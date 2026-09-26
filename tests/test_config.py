import pytest

from hailer.config import load_config
from hailer.errors import ConfigError


def test_example_config_parses():
    from pathlib import Path

    cfg = load_config(Path(__file__).resolve().parents[1] / "config.example.toml")
    assert cfg.notify_to == "sam@example.com"
    assert cfg.notify_from == "sam.watch@gmail.com"
    assert cfg.concurrency == 10


def test_env_path_and_defaults(tmp_path, monkeypatch):
    path = tmp_path / "custom.toml"
    path.write_text('notify_to = "a@example.com"\nnotify_from = "B@Example.com"\n', encoding="utf-8")
    monkeypatch.setenv("HAILER_CONFIG", str(path))
    cfg = load_config()
    assert cfg.notify_from == "b@example.com"
    assert cfg.concurrency == 10


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(tmp_path / "missing.toml")


def test_rejects_bad_concurrency_and_email(tmp_path):
    path = tmp_path / "hailer.toml"
    path.write_text(
        'notify_to = "not-an-email"\nnotify_from = "a@example.com"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)
    path.write_text(
        'notify_to = "a@example.com"\nnotify_from = "b@example.com"\nconcurrency = true\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="integer"):
        load_config(path)
    path.write_text(
        'notify_to = "a@example.com"\nnotify_from = "b@example.com"\nconcurrency = 0\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="at least 1"):
        load_config(path)
