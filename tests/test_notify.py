import base64

from hailer.notify import build_notification


def test_notification_contains_the_required_fields_and_not_the_body():
    raw = build_notification(
        notify_to="sam@example.com",
        notify_from="sam.watch@gmail.com",
        account="other.inbox@gmail.com",
        classification="recruiter",
        sender="Jordan Lee <jordan@greenhouse.io>",
        subject="Interview for backend engineer",
        message_id="18d2f0ab12c3ef45",
    )
    text = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
    assert "To: sam@example.com" in text
    assert "From: sam.watch@gmail.com" in text
    assert "X-Hailer: notification" in text
    assert "Account: other.inbox@gmail.com" in text
    assert "Classification: recruiter" in text
    assert "From: Jordan Lee <jordan@greenhouse.io>" in text
    assert "Subject: Interview for backend engineer" in text
    assert "Gmail message id: 18d2f0ab12c3ef45" in text
    assert "snippet" not in text.lower()


def test_subject_newlines_cannot_inject_headers():
    raw = build_notification(
        notify_to="sam@example.com",
        notify_from="sam.watch@gmail.com",
        account="other.inbox@gmail.com",
        classification="autoreply",
        sender="Bot <bot@example.com>",
        subject="Out of office\r\nBcc: attacker@example.com",
        message_id="m1",
    )
    text = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8").replace("\r\n", "\n")
    header_block, _, body = text.partition("\n\n")
    names = [
        line.split(":", 1)[0].lower()
        for line in header_block.split("\n")
        if line and not line[0].isspace()
    ]
    assert "bcc" not in names
    assert "Out of office Bcc: attacker@example.com" in text
    assert body.count("\nBcc:") == 0
