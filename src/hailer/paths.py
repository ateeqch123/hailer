"""Local paths for tokens and the dedup database. Nothing here is committed."""

from __future__ import annotations

import os
from pathlib import Path

TOKEN_DIR_ENV = "HAILER_TOKEN_DIR"
STATE_DB_ENV = "HAILER_STATE_DB"


def data_home() -> Path:
    return Path.home() / ".local" / "share" / "hailer"


def token_dir() -> Path:
    override = os.environ.get(TOKEN_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return data_home() / "tokens"


def state_db() -> Path:
    override = os.environ.get(STATE_DB_ENV)
    if override:
        return Path(override).expanduser()
    return data_home() / "notified.db"
