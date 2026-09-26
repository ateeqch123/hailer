"""Classify one message. Pure function: no network and no disk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from email.utils import parseaddr
from typing import Literal

Classification = Literal["recruiter", "autoreply", "ignore"]

# Sender domain, or any subdomain of it, counts as a recruiting system.
RECRUITER_DOMAINS: tuple[str, ...] = (
    "greenhouse.io",
    "lever.co",
    "linkedin.com",
    "indeed.com",
    "ashbyhq.com",
    "myworkday.com",
)

# Whole words, plus the plurals recruiters, opportunities, and interviews.
RECRUITER_WORDS: tuple[str, ...] = (
    "recruiter",
    "opportunity",
    "interview",
    "hiring",
)

# Case-insensitive phrases in the subject or the Gmail snippet.
AUTOREPLY_PHRASES: tuple[str, ...] = (
    "out of office",
    "out-of-office",
    "automatic reply",
    "automatic response",
    "auto-reply",
    "auto reply",
    "autoreply",
    "away from the office",
    "away from office",
    "on vacation",
    "i am currently out",
    "i'm currently out",
    "this is an automatic",
)

_WORD_RE = re.compile(
    r"\b(?:recruiters?|opportunit(?:y|ies)|interviews?|hiring)\b",
    re.IGNORECASE,
)
_PHRASE_RE = re.compile(
    "|".join(re.escape(phrase) for phrase in AUTOREPLY_PHRASES),
    re.IGNORECASE,
)


def classify(headers: Mapping[str, str], snippet: str | None = None) -> Classification:
    """Return recruiter, autoreply, or ignore.

    Autoreply wins. An out-of-office note that mentions an interview stays an
    autoreply. Date, Precedence, and List-Id are not classification inputs.
    """
    folded = _fold(headers)
    text = _text(folded, snippet)
    if _is_autoreply(folded, text):
        return "autoreply"
    if _is_recruiter(folded, text):
        return "recruiter"
    return "ignore"


def _fold(headers: Mapping[str, str]) -> dict[str, str]:
    folded: dict[str, str] = {}
    for key, value in headers.items():
        name = str(key).strip().lower()
        if not name or name in folded:
            continue
        folded[name] = "" if value is None else str(value)
    return folded


def _text(headers: Mapping[str, str], snippet: str | None) -> str:
    parts = [headers.get("subject", "")]
    if snippet:
        parts.append(snippet)
    return "\n".join(parts)


def _is_autoreply(headers: Mapping[str, str], text: str) -> bool:
    auto = headers.get("auto-submitted", "").strip().lower()
    if auto and auto != "no":
        return True
    return _PHRASE_RE.search(text) is not None


def _is_recruiter(headers: Mapping[str, str], text: str) -> bool:
    if _domain_is_recruiter(_sender_domain(headers.get("from", ""))):
        return True
    return _WORD_RE.search(text) is not None


def _sender_domain(from_header: str) -> str:
    _name, address = parseaddr(from_header)
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[1].strip().lower().rstrip(".")


def _domain_is_recruiter(domain: str) -> bool:
    for suffix in RECRUITER_DOMAINS:
        if domain == suffix or domain.endswith("." + suffix):
            return True
    return False
