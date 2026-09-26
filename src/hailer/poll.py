"""Poll authorized accounts on a bounded thread pool and notify once."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

from hailer.classify import Classification, classify
from hailer.config import MAX_ACCOUNTS
from hailer.errors import NotifyFromNotAuthorized, TooManyAccounts
from hailer.messages import Message
from hailer.notify import build_notification
from hailer.store import DedupStore

logger = logging.getLogger("hailer")


class MailClient(Protocol):
    def list_unread_ids(self, account: str) -> list[str]:
        """Recent unread inbox message ids for one authorized account."""

    def get_message(self, account: str, message_id: str) -> Message:
        """Metadata for one message. Must not be required to return the body."""

    def send_raw(self, account: str, raw: str) -> None:
        """Send a base64url RFC 2822 message as this authorized account."""


@dataclass(frozen=True)
class Action:
    account: str
    message_id: str
    classification: Classification
    sender: str
    subject: str
    notified: bool
    skipped_duplicate: bool
    dry_run: bool


@dataclass(frozen=True)
class AccountError:
    account: str
    message_id: str | None
    error: str


@dataclass
class CheckReport:
    actions: list[Action] = field(default_factory=list)
    errors: list[AccountError] = field(default_factory=list)


def format_action(action: Action) -> str:
    if action.skipped_duplicate:
        status = "skip-duplicate"
    elif action.dry_run:
        status = "dry-run"
    elif action.notified:
        status = "notified"
    else:
        status = "recorded"
    return (
        f"{status} label={action.classification} account={action.account} "
        f"message_id={action.message_id} from={_one_line(action.sender)} "
        f"subject={_one_line(action.subject)}"
    )


def run_check(
    accounts: list[str],
    client: MailClient,
    store: DedupStore,
    *,
    notify_to: str,
    notify_from: str,
    concurrency: int,
    dry_run: bool,
) -> CheckReport:
    """Poll every account, at most `concurrency` at a time.

    Sends from notify_from, which must itself be in `accounts`. Dry-run
    classifies and returns actions without sending or writing the dedup db.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    normalized = [account.strip().lower() for account in accounts]
    sender = notify_from.strip().lower()
    if len(normalized) > MAX_ACCOUNTS:
        raise TooManyAccounts(
            f"hailer watches at most {MAX_ACCOUNTS} accounts (found {len(normalized)})"
        )
    if sender not in normalized:
        raise NotifyFromNotAuthorized(
            f"notify_from {sender} is not an authorized account. "
            "Run `hailer auth add` while signed in to that account."
        )

    report = CheckReport()
    report_lock = threading.Lock()

    def worker(account: str) -> None:
        actions, errors = check_account(
            account,
            client=client,
            store=store,
            notify_to=notify_to,
            notify_from=sender,
            dry_run=dry_run,
        )
        with report_lock:
            report.actions.extend(actions)
            report.errors.extend(errors)

    workers = min(concurrency, len(normalized))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(worker, normalized))

    report.actions.sort(key=lambda item: (item.account, item.message_id))
    report.errors.sort(key=lambda item: (item.account, item.message_id or ""))
    logger.info(
        "accounts=%s actions=%s errors=%s dry_run=%s",
        len(normalized),
        len(report.actions),
        len(report.errors),
        dry_run,
    )
    return report


def check_account(
    account: str,
    *,
    client: MailClient,
    store: DedupStore,
    notify_to: str,
    notify_from: str,
    dry_run: bool,
) -> tuple[list[Action], list[AccountError]]:
    actions: list[Action] = []
    errors: list[AccountError] = []
    try:
        message_ids = client.list_unread_ids(account)
    except Exception as exc:
        _log_error(account, None, exc)
        errors.append(AccountError(account, None, type(exc).__name__))
        return actions, errors

    for message_id in message_ids:
        try:
            action = _one_message(
                account,
                message_id,
                client=client,
                store=store,
                notify_to=notify_to,
                notify_from=notify_from,
                dry_run=dry_run,
            )
        except Exception as exc:
            _log_error(account, message_id, exc)
            errors.append(AccountError(account, message_id, type(exc).__name__))
            continue
        if action is not None:
            actions.append(action)
    return actions, errors


def _one_message(
    account: str,
    message_id: str,
    *,
    client: MailClient,
    store: DedupStore,
    notify_to: str,
    notify_from: str,
    dry_run: bool,
) -> Action | None:
    message = client.get_message(account, message_id)
    if _is_hailer_notice(message):
        logger.info(
            "account=%s message_id=%s label=%s",
            account,
            message.message_id,
            "ignore",
        )
        return None
    label = classify(message.headers, message.snippet or None)
    logger.info(
        "account=%s message_id=%s label=%s",
        account,
        message.message_id,
        label,
    )
    if label == "ignore":
        return None
    if store.already_notified(account, message.message_id):
        return Action(
            account=account,
            message_id=message.message_id,
            classification=label,
            sender=message.sender,
            subject=message.subject,
            notified=False,
            skipped_duplicate=True,
            dry_run=dry_run,
        )
    if dry_run:
        return Action(
            account=account,
            message_id=message.message_id,
            classification=label,
            sender=message.sender,
            subject=message.subject,
            notified=False,
            skipped_duplicate=False,
            dry_run=True,
        )
    raw = build_notification(
        notify_to=notify_to,
        notify_from=notify_from,
        account=account,
        classification=label,
        sender=message.sender,
        subject=message.subject,
        message_id=message.message_id,
    )
    client.send_raw(notify_from, raw)
    store.mark_notified(account, message.message_id, label)
    return Action(
        account=account,
        message_id=message.message_id,
        classification=label,
        sender=message.sender,
        subject=message.subject,
        notified=True,
        skipped_duplicate=False,
        dry_run=False,
    )


def _is_hailer_notice(message: Message) -> bool:
    """Skip hailer's own alerts so a notice is not classified as recruiter mail."""
    if message.headers.get("x-hailer", "").strip().lower() == "notification":
        return True
    return message.subject.lstrip().lower().startswith("[hailer]")


def _log_error(account: str, message_id: str | None, exc: BaseException) -> None:
    logger.error(
        "account=%s message_id=%s error=%s",
        account,
        message_id or "-",
        type(exc).__name__,
    )


def _one_line(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())
