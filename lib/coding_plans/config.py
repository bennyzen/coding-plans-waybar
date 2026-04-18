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
        "bar_format": "{short_pct}%·{weekly_pct}%",
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
    # Default module styling. Every value here is a CSS fragment emitted by
    # the installer into each ``#custom-coding-plans-<id>`` rule. Override
    # per-provider via ``[providers.<id>.style]``.
    "style": {
        "font_family":      "",           # empty → inherit from Waybar bar
        "font_size":        "11px",
        "font_weight":      "",
        "letter_spacing":   "0.02em",
        "padding":          "0 8px 0 23px",
        "margin":           "0 3px",
        "icon_size":        "13px",
        "icon_position":    "6px center",
        # Optional coloured disc behind the icon. Useful when a mono brand
        # SVG (e.g. Z.AI's black glyph) vanishes against a dark bar.
        "icon_bg_color":    "",           # "" = no backdrop; e.g. "#ffffff"
        "icon_bg_padding":  "2px",        # ring width around the icon
        "border_radius":    "",           # e.g. "10px" for pill, "" for square
        "color":            "@foreground",
        "fresh_opacity":    0.92,
        "stale_opacity":    0.4,
        "empty_opacity":    0.28,
        "critical_color":   "#c9a227",
        "critical_weight":  "700",
        "exhausted_color":  "#d24646",
        "exhausted_weight": "700",
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
