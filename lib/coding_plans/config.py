"""TOML config loader with defaults + deep merge."""

from __future__ import annotations

import sys
from typing import Any

try:
    import tomllib
except ImportError:  # py < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from .paths import CONFIG_PATH

DEFAULT_CONFIG: dict[str, Any] = {
    "display": {
        "bar_format": "{icon} {short_pct}%·{weekly_pct}%",
        "join": "  ",
        "show_empty_providers": False,
    },
    "behavior": {
        "stale_after_seconds": 300,
    },
    "thresholds": {
        "critical": 80,
        "exhausted": 100,
    },
    "tooltip": {
        "show_progress_bars": True,
        "show_today": True,
        "show_updated_ago": True,
        "bar_width": 10,
    },
    # Providers are populated by the user's config file. Defaults are empty —
    # a provider has to be explicitly enabled to render.
    "providers": {},
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG
    try:
        with CONFIG_PATH.open("rb") as fh:
            user = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"coding-plans: config read failed, using defaults ({exc})", file=sys.stderr)
        return DEFAULT_CONFIG
    return _deep_merge(DEFAULT_CONFIG, user)
