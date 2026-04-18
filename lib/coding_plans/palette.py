"""Baked semantic palette + Omarchy theme overlay.

Ported from upstream claude_usage.py.

Accents (healthy → danger) are BAKED — harvesting them from alacritty's ANSI
slots broke on non-IBM themes where red means red and healthy usage would
paint red. Never again: accents stay baked. Only chrome (bg, surface, text,
border) comes from the active theme.
"""

from __future__ import annotations

import re
from pathlib import Path

BAKED_PALETTE = {
    "bg":      "#0a0d10",
    "surface": "#050709",
    "text":    "#ffffff",
    "muted":   "#727272",
    "border":  "#4a4a4a",
    "accent":  "#66a773",   # healthy
    "warn":    "#b4b47b",   # 80%+
    "crit":    "#993426",   # 100%+
    "danger":  "#d24646",   # hard-exhausted
}


def load_palette() -> dict[str, str]:
    """Overlay chrome colours from the active Omarchy theme."""
    theme_dir = Path.home() / ".config" / "omarchy" / "current" / "theme"
    p = dict(BAKED_PALETTE)
    for src in ("waybar.css", "walker.css"):
        try:
            text = (theme_dir / src).read_text(encoding="utf-8")
        except OSError:
            continue
        for name, hex_ in re.findall(
            r'@define-color\s+(\w+)\s+(#[0-9a-fA-F]+)',
            text,
        ):
            if name in ("background", "base"):
                p["surface"] = hex_
                p["bg"] = hex_
            elif name == "foreground":
                p["text"] = hex_
            elif name == "border":
                p["border"] = hex_
    return p


def pct_color(pct: int | None, palette: dict[str, str], critical: int, exhausted: int) -> str:
    """Pick a palette colour for a percentage against the two thresholds."""
    if pct is None:
        return palette["muted"]
    if pct >= exhausted:
        return palette["danger"]
    if pct >= critical:
        return palette["crit"]
    if pct >= 50:
        return palette["warn"]
    return palette["accent"]
