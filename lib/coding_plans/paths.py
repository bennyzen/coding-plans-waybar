"""XDG paths — shared by every subsystem."""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "coding-plans"
)
CACHE_DIR = (
    Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "coding-plans"
)
CONFIG_PATH = CONFIG_DIR / "config.toml"
STATE_PATH = CACHE_DIR / "state.json"
