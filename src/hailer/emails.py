"""Email address checks shared by config and token filenames."""

from __future__ import annotations

import re

from hailer.errors import HailerError

EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if EMAIL_RE.fullmatch(email):
        return email
    shown = " ".join(value.split())
    if len(shown) > 80:
        shown = shown[:77] + "..."
    raise HailerError(f"not an email address: {shown!r}")
