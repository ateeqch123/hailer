import json
from pathlib import Path

import pytest

from hailer.auth import SCOPES, add_account, list_accounts
from hailer.cli import main
from hailer.errors import TooManyAccounts


class _Creds:
    def to_json(self):
        return '{"token": "test-token"}'


class _Flow:
    @classmethod
    def from_client_secrets_file(cls, path, scopes):
        assert scopes == SCOPES
        assert Path(path).is_file()
        return cls()

    def run_local_server(self, **kwargs):
        assert kwargs["port"] == 0
        assert kwargs["access_type"] == "offline"
        assert kwargs["prompt"] == "consent"
        return _Creds()


class _Profile:
    def __init__(self, email):
        self.email = email

    def users(self):
        return self

    def getProfile(self, userId):
        assert userId == "me"
        return self

    def execute(self):
        return {"emailAddress": self.email}


def test_add_account_saves_one_token(tmp_path, monkeypatch, capsys):
    secret = tmp_path / "client_secret.json"
    secret.write_text("{}", encoding="utf-8")
    seen = {}

    def fake_build(api, version, credentials=None, cache_discovery=None):
        seen["api"] = (api, version, cache_discovery)
        assert credentials is not None
        return _Profile("Owner@Gmail.com")

    monkeypatch.setattr("hailer.auth.InstalledAppFlow", _Flow)
    monkeypatch.setattr("hailer.auth.build", fake_build)
    code = main(["auth", "add", "--client-secret", str(secret)])
    assert code == 0
    captured = capsys.readouterr()
    assert "Connected owner@gmail.com." in captured.out
    assert "test-token" not in captured.out
    assert "test-token" not in captured.err
    assert seen["api"] == ("gmail", "v1", False)
    saved = tmp_path / "tokens" / "owner@gmail.com.json"
    assert saved.read_text(encoding="utf-8") == '{"token": "test-token"}'
    assert saved.stat().st_mode & 0o777 == 0o600
    assert list_accounts(tmp_path / "tokens") == ["owner@gmail.com"]


def test_add_refuses_a_101st_account_and_allows_reauth(tmp_path, monkeypatch):
    secret = tmp_path / "client_secret.json"
    secret.write_text("{}", encoding="utf-8")
    tokens = tmp_path / "tokens"
    tokens.mkdir()
    for index in range(100):
        (tokens / f"u{index}@example.com.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("hailer.auth.InstalledAppFlow", _Flow)
    monkeypatch.setattr("hailer.auth.build", lambda *args, **kwargs: _Profile("new@example.com"))
    with pytest.raises(TooManyAccounts):
        add_account(secret, tokens)
    assert not (tokens / "new@example.com.json").exists()

    monkeypatch.setattr("hailer.auth.build", lambda *args, **kwargs: _Profile("u0@example.com"))
    assert add_account(secret, tokens) == "u0@example.com"
    assert "test-token" in (tokens / "u0@example.com.json").read_text(encoding="utf-8")


def test_list_ignores_non_email_files(tmp_path):
    tokens = tmp_path / "tokens"
    tokens.mkdir()
    (tokens / "b@example.com.json").write_text("{}", encoding="utf-8")
    (tokens / "a@example.com.json").write_text("{}", encoding="utf-8")
    (tokens / "notes.json").write_text("{}", encoding="utf-8")
    assert list_accounts(tokens) == ["a@example.com", "b@example.com"]


def test_client_secret_example_is_a_placeholder():
    path = Path(__file__).resolve().parents[1] / "client_secret.json.example"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["installed"]["client_secret"] == "YOUR_CLIENT_SECRET"
    assert "YOUR_CLIENT_ID" in data["installed"]["client_id"]
