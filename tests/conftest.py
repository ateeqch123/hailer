import pytest

from hailer.paths import state_db, token_dir


@pytest.fixture(autouse=True)
def isolate_hailer_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HAILER_TOKEN_DIR", str(tmp_path / "tokens"))
    monkeypatch.setenv("HAILER_STATE_DB", str(tmp_path / "notified.db"))
    monkeypatch.delenv("HAILER_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_defaults_follow_the_env(tmp_path):
    assert token_dir() == tmp_path / "tokens"
    assert state_db() == tmp_path / "notified.db"
