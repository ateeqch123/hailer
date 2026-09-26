"""Gmail message metadata, parsed without calling the network."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from email.header import decode_header

METADATA_HEADERS: tuple[str, ...] = (
    "From",
    "Subject",
    "Date",
    "Auto-Submitted",
    "Precedence",
    "List-Id",
    "X-Hailer",
)


@dataclass(frozen=True)
class Message:
    message_id: str
    headers: dict[str, str]
    snippet: str

    @property
    def sender(self) -> str:
        return self.headers.get("from", "")

    @property
    def subject(self) -> str:
        return self.headers.get("subject", "")


def decode_mime_header(value: str) -> str:
    if not value:
        return ""
    chunks: list[str] = []
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            chunks.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            chunks.append(text)
    return "".join(chunks)


def headers_from_api_payload(payload_headers: list[Mapping[str, object]]) -> dict[str, str]:
    """Lower-case header names. The first value wins when a name is repeated."""
    folded: dict[str, str] = {}
    for item in payload_headers:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name", "")).strip().lower()
        if not name or name in folded:
            continue
        folded[name] = decode_mime_header(str(item.get("value", "")))
    return folded


def message_from_api_response(response: Mapping[str, object]) -> Message:
    payload = response.get("payload") or {}
    if not isinstance(payload, Mapping):
        payload = {}
    raw_headers = payload.get("headers") or []
    headers = headers_from_api_payload(raw_headers if isinstance(raw_headers, list) else [])
    snippet = response.get("snippet") or ""
    return Message(
        message_id=str(response["id"]),
        headers=headers,
        snippet=str(snippet),
    )


def message_ids_from_list_response(response: Mapping[str, object]) -> list[str]:
    messages = response.get("messages") or []
    if not isinstance(messages, list):
        return []
    ids: list[str] = []
    for item in messages:
        if isinstance(item, Mapping) and item.get("id"):
            ids.append(str(item["id"]))
    return ids
