"""Load hailer.toml. HAILER_CONFIG overrides the default path ./hailer.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from hailer.emails import normalize_email
from hailer.errors import ConfigError, HailerError

DEFAULT_CONCURRENCY = 10
MAX_ACCOUNTS = 100
CONFIG_ENV = "HAILER_CONFIG"


@dataclass(frozen=True)
class Config:
    notify_to: str
    notify_from: str
    concurrency: int = DEFAULT_CONCURRENCY


def load_config(path: Path | None = None) -> Config:
    if path is None:
        override = os.environ.get(CONFIG_ENV)
        path = Path(override).expanduser() if override else Path("hailer.toml")
    if not path.is_file():
        raise ConfigError(
            f"config file not found: {path}. Copy config.example.toml to hailer.toml "
            f"or set {CONFIG_ENV}."
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"could not parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a TOML table")

    try:
        notify_to = normalize_email(str(data.get("notify_to", "")))
        notify_from = normalize_email(str(data.get("notify_from", "")))
    except HailerError as exc:
        raise ConfigError(str(exc)) from exc

    concurrency = data.get("concurrency", DEFAULT_CONCURRENCY)
    if isinstance(concurrency, bool) or not isinstance(concurrency, int):
        raise ConfigError("concurrency must be an integer")
    if concurrency < 1:
        raise ConfigError("concurrency must be at least 1")
    return Config(notify_to=notify_to, notify_from=notify_from, concurrency=concurrency)
