"""Gmail API adapter. Callers pass an account that already completed OAuth."""

from __future__ import annotations

import threading
from pathlib import Path

from googleapiclient.discovery import build

from hailer.auth import load_credentials
from hailer.messages import (
    METADATA_HEADERS,
    Message,
    message_from_api_response,
    message_ids_from_list_response,
)

MAX_MESSAGES_PER_ACCOUNT = 25
UNREAD_QUERY = "is:unread in:inbox"


class GmailApiClient:
    def __init__(self, token_dir: Path):
        self.token_dir = token_dir
        self._services: dict[str, object] = {}
        self._lock = threading.Lock()

    def list_unread_ids(self, account: str) -> list[str]:
        service = self._service(account)
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=UNREAD_QUERY,
                maxResults=MAX_MESSAGES_PER_ACCOUNT,
            )
            .execute()
        )
        return message_ids_from_list_response(response)

    def get_message(self, account: str, message_id: str) -> Message:
        service = self._service(account)
        response = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=list(METADATA_HEADERS),
            )
            .execute()
        )
        return message_from_api_response(response)

    def send_raw(self, account: str, raw: str) -> None:
        service = self._service(account)
        service.users().messages().send(userId="me", body={"raw": raw}).execute()

    def _service(self, account: str):
        with self._lock:
            cached = self._services.get(account)
            if cached is not None:
                return cached
            creds = load_credentials(self.token_dir / f"{account}.json")
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            self._services[account] = service
            return service
