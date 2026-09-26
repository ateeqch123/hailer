"""Installed-app OAuth. One consent screen, one token file, per account."""

from __future__ import annotations

from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from hailer.config import MAX_ACCOUNTS
from hailer.emails import EMAIL_RE, normalize_email
from hailer.errors import TooManyAccounts

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def list_accounts(token_dir: Path) -> list[str]:
    if not token_dir.is_dir():
        return []
    found: list[str] = []
    for path in token_dir.glob("*.json"):
        name = path.name[: -len(".json")].lower()
        if EMAIL_RE.fullmatch(name):
            found.append(name)
    return sorted(found)


def add_account(client_secret: Path, token_dir: Path) -> str:
    """Run Google's installed-app consent flow and save that account's token.

    The operator repeats this once per Gmail account, up to MAX_ACCOUNTS.
    Each account owner has to approve the consent screen. Hailer never asks
    for a password.
    """
    if not client_secret.is_file():
        raise FileNotFoundError(
            f"OAuth client file not found: {client_secret}. "
            "Download a Desktop client JSON from Google Cloud and pass it with "
            "--client-secret. See README.md."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    email = normalize_email(str(profile.get("emailAddress", "")))

    existing = list_accounts(token_dir)
    if email not in existing and len(existing) >= MAX_ACCOUNTS:
        raise TooManyAccounts(
            f"hailer stores at most {MAX_ACCOUNTS} accounts. "
            "Remove a token file before adding another."
        )

    token_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    token_dir.chmod(0o700)
    path = token_dir / f"{email}.json"
    path.write_text(creds.to_json(), encoding="utf-8")
    path.chmod(0o600)
    return email


def load_credentials(path: Path) -> Credentials:
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
        path.chmod(0o600)
    return creds
