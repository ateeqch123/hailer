import logging
import threading

import pytest

from hailer.errors import NotifyFromNotAuthorized, TooManyAccounts
from hailer.messages import Message
from hailer.poll import run_check
from hailer.store import DedupStore


class FakeGmail:
    def __init__(self, boxes):
        self.boxes = boxes
        self.sent = []
        self.lock = threading.Lock()

    def list_unread_ids(self, account):
        return [message.message_id for message in self.boxes.get(account, [])]

    def get_message(self, account, message_id):
        for message in self.boxes.get(account, []):
            if message.message_id == message_id:
                return message
        raise KeyError(message_id)

    def send_raw(self, account, raw):
        with self.lock:
            self.sent.append((account, raw))


def _message(message_id, sender, subject, snippet="", extra=None):
    headers = {"from": sender, "subject": subject}
    if extra:
        headers.update(extra)
    return Message(message_id=message_id, headers=headers, snippet=snippet)


def _run(tmp_path, client, accounts, dry_run=False, concurrency=4, notify_from="watch@example.com"):
    store = DedupStore(tmp_path / "notified.db")
    try:
        report = run_check(
            accounts,
            client,
            store,
            notify_to="sam@example.com",
            notify_from=notify_from,
            concurrency=concurrency,
            dry_run=dry_run,
        )
    finally:
        store.close()
    return report, DedupStore(tmp_path / "notified.db")


def test_recruiter_and_autoreply_send_once_from_notify_from(tmp_path):
    client = FakeGmail(
        {
            "watch@example.com": [
                _message("m-rec", "Jordan <jordan@greenhouse.io>", "Hello there"),
                _message(
                    "m-auto",
                    "Jordan <jordan@greenhouse.io>",
                    "Interview tomorrow",
                    extra={"auto-submitted": "auto-replied"},
                ),
                _message("m-ignore", "ada@example.com", "Lunch plans"),
            ]
        }
    )
    report, store = _run(tmp_path, client, ["watch@example.com"])
    store.close()
    labels = {action.message_id: action.classification for action in report.actions}
    assert labels == {"m-rec": "recruiter", "m-auto": "autoreply"}
    assert all(action.notified for action in report.actions)
    assert [account for account, _raw in client.sent] == ["watch@example.com", "watch@example.com"]
    assert report.errors == []


def test_second_poll_skips_duplicates(tmp_path):
    boxes = {
        "watch@example.com": [_message("m1", "a@lever.co", "Hello")],
        "other@example.com": [_message("m1", "a@lever.co", "Hello")],
    }
    client = FakeGmail(boxes)
    accounts = ["watch@example.com", "other@example.com"]
    first, _store = _run(tmp_path, client, accounts)
    _store.close()
    assert len(client.sent) == 2
    second, store = _run(tmp_path, client, accounts)
    store.close()
    assert len(client.sent) == 2
    assert {action.skipped_duplicate for action in second.actions} == {True}
    assert len(first.actions) == 2


def test_dry_run_does_not_send_or_record(tmp_path):
    client = FakeGmail({"watch@example.com": [_message("m1", "a@indeed.com", "Hello")]})
    report, store = _run(tmp_path, client, ["watch@example.com"], dry_run=True)
    assert report.actions[0].dry_run is True
    assert report.actions[0].notified is False
    assert client.sent == []
    assert store.already_notified("watch@example.com", "m1") is False
    store.close()

    again, store2 = _run(tmp_path, client, ["watch@example.com"], dry_run=False)
    store2.close()
    assert again.actions[0].notified is True
    assert len(client.sent) == 1


def test_cross_account_notification_names_the_inbox(tmp_path):
    client = FakeGmail({"other@example.com": [_message("m9", "a@ashbyhq.com", "Next step")]})
    report, store = _run(
        tmp_path,
        client,
        ["watch@example.com", "other@example.com"],
    )
    store.close()
    assert report.actions[0].account == "other@example.com"
    assert client.sent[0][0] == "watch@example.com"
    import base64

    body = base64.urlsafe_b64decode(client.sent[0][1].encode()).decode()
    assert "Account: other@example.com" in body
    assert "Gmail message id: m9" in body
    assert "Classification: recruiter" in body


def test_hailer_notice_is_not_notified(tmp_path):
    client = FakeGmail(
        {
            "watch@example.com": [
                _message(
                    "loop",
                    "sam.watch@gmail.com",
                    "[hailer] recruiter on watch@example.com: Interview",
                    snippet="Classification: recruiter",
                )
            ]
        }
    )
    report, store = _run(tmp_path, client, ["watch@example.com"])
    store.close()
    assert report.actions == []
    assert client.sent == []


def test_x_hailer_header_is_ignored(tmp_path):
    client = FakeGmail(
        {
            "watch@example.com": [
                _message(
                    "loop",
                    "ada@example.com",
                    "Hello",
                    snippet="a recruiter wrote",
                    extra={"x-hailer": "notification"},
                )
            ]
        }
    )
    report, store = _run(tmp_path, client, ["watch@example.com"])
    store.close()
    assert report.actions == []
    assert client.sent == []


def test_one_account_error_does_not_stop_the_other(tmp_path):
    class Partial(FakeGmail):
        def list_unread_ids(self, account):
            if account == "bad@example.com":
                raise RuntimeError("token exploded SECRET_SHOULD_NOT_LEAK")
            return super().list_unread_ids(account)

    client = Partial({"good@example.com": [_message("m1", "a@myworkday.com", "Hello")]})
    report, store = _run(
        tmp_path,
        client,
        ["bad@example.com", "good@example.com", "watch@example.com"],
    )
    store.close()
    assert [action.message_id for action in report.actions] == ["m1"]
    assert report.errors == [
        type(report.errors[0])("bad@example.com", None, "RuntimeError")
    ]
    assert "SECRET" not in report.errors[0].error


def test_send_failure_is_not_marked(tmp_path, caplog):
    class SendFails(FakeGmail):
        def send_raw(self, account, raw):
            raise RuntimeError("send failed SECRET_BODY")

    client = SendFails({"watch@example.com": [_message("m1", "a@linkedin.com", "Hello")]})
    with caplog.at_level(logging.DEBUG, logger="hailer"):
        report, store = _run(tmp_path, client, ["watch@example.com"])
    assert store.already_notified("watch@example.com", "m1") is False
    store.close()
    assert report.errors[0].error == "RuntimeError"
    assert "SECRET_BODY" not in caplog.text
    assert "Hello" not in caplog.text
    assert "label=recruiter" in caplog.text
    assert "message_id=m1" in caplog.text


def test_logs_omit_subject_and_snippet(tmp_path, caplog):
    client = FakeGmail(
        {
            "watch@example.com": [
                _message(
                    "m1",
                    "ada@example.com",
                    "UNIQUE_SUBJECT hiring",
                    snippet="UNIQUE_SNIPPET_BODY",
                )
            ]
        }
    )
    with caplog.at_level(logging.DEBUG, logger="hailer"):
        report, store = _run(tmp_path, client, ["watch@example.com"])
    store.close()
    assert report.actions[0].classification == "recruiter"
    assert "UNIQUE_SUBJECT" not in caplog.text
    assert "UNIQUE_SNIPPET_BODY" not in caplog.text
    assert "account=watch@example.com" in caplog.text
    assert "message_id=m1" in caplog.text
    assert "label=recruiter" in caplog.text


def test_notify_from_must_be_authorized(tmp_path):
    client = FakeGmail({})

    def explode(self, account):
        raise AssertionError("should not poll")

    client.list_unread_ids = explode
    store = DedupStore(tmp_path / "notified.db")
    with pytest.raises(NotifyFromNotAuthorized):
        run_check(
            ["a@example.com"],
            client,
            store,
            notify_to="sam@example.com",
            notify_from="missing@example.com",
            concurrency=2,
            dry_run=True,
        )
    store.close()


def test_account_cap(tmp_path):
    accounts = [f"u{i}@example.com" for i in range(101)]
    accounts.append("watch@example.com")
    client = FakeGmail({})
    client.list_unread_ids = lambda account: (_ for _ in ()).throw(AssertionError("polled"))
    store = DedupStore(tmp_path / "notified.db")
    with pytest.raises(TooManyAccounts):
        run_check(
            accounts,
            client,
            store,
            notify_to="sam@example.com",
            notify_from="watch@example.com",
            concurrency=10,
            dry_run=True,
        )
    store.close()


def test_one_hundred_accounts_are_allowed(tmp_path):
    accounts = [f"u{index}@example.com" for index in range(99)]
    accounts.append("watch@example.com")
    report, store = _run(tmp_path, FakeGmail({}), accounts, concurrency=10)
    store.close()
    assert len(accounts) == 100
    assert report.actions == []
    assert report.errors == []


def test_concurrency_is_bounded(tmp_path):
    class Probe:
        def __init__(self):
            self.lock = threading.Lock()
            self.inside = 0
            self.max_seen = 0
            self.failed = False
            self.barrier = threading.Barrier(2, timeout=3)

        def list_unread_ids(self, account):
            with self.lock:
                self.inside += 1
                self.max_seen = max(self.max_seen, self.inside)
            try:
                self.barrier.wait()
            except threading.BrokenBarrierError:
                self.failed = True
            finally:
                with self.lock:
                    self.inside -= 1
            return []

        def get_message(self, account, message_id):
            raise AssertionError(message_id)

        def send_raw(self, account, raw):
            raise AssertionError("send")

    probe = Probe()
    accounts = ["watch@example.com", "b@example.com", "c@example.com", "d@example.com"]
    report, store = _run(tmp_path, probe, accounts, concurrency=2)
    store.close()
    assert probe.max_seen == 2
    assert probe.failed is False
    assert report.errors == []
    assert report.actions == []


def test_mixed_case_notify_from_matches(tmp_path):
    client = FakeGmail({"watch@example.com": [_message("m1", "a@example.com", "We are hiring")]})
    report, store = _run(
        tmp_path,
        client,
        ["Watch@Example.com"],
        notify_from="Watch@Example.com",
    )
    store.close()
    assert report.actions[0].account == "watch@example.com"
    assert client.sent[0][0] == "watch@example.com"
