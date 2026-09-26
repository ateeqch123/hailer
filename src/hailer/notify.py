"""Build the one notification email hailer sends through the Gmail API."""

from __future__ import annotations

import base64
from email.message import EmailMessage


def build_notification(
    *,
    notify_to: str,
    notify_from: str,
    account: str,
    classification: str,
    sender: str,
    subject: str,
    message_id: str,
) -> str:
    """Return the base64url raw string for users.messages.send.

    The body has the receiving account, classification, from, subject, and
    Gmail message id. It does not include the message body or snippet.
    """
    mail = EmailMessage()
    mail["To"] = notify_to
    mail["From"] = notify_from
    mail["X-Hailer"] = "notification"
    short_subject = _one_line(subject, limit=80)
    if short_subject:
        mail["Subject"] = f"[hailer] {classification} on {account}: {short_subject}"
    else:
        mail["Subject"] = f"[hailer] {classification} on {account}"
    mail.set_content(
        "\n".join(
            [
                "Hailer classified a Gmail message.",
                "",
                f"Account: {account}",
                f"Classification: {classification}",
                f"From: {_one_line(sender)}",
                f"Subject: {_one_line(subject, limit=500)}",
                f"Gmail message id: {message_id}",
                "",
            ]
        )
    )
    return base64.urlsafe_b64encode(mail.as_bytes()).decode("ascii")


def _one_line(value: str, limit: int | None = None) -> str:
    text = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    if limit is not None and len(text) > limit:
        return text[: limit - 3] + "..."
    return text
