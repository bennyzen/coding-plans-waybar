#!/usr/bin/env python3
"""Generate the Waybar ``module.jsonc`` + ``style.css`` snippets from whatever
providers are enabled in ``~/.config/coding-plans/config.toml``.

One Waybar custom module per enabled provider::

    custom/coding-plans-claude    -> fetches Claude only
    custom/coding-plans-zai       -> fetches Z.AI only

Each module's CSS carries a ``background-image`` pointing at that provider's
SVG so Waybar shows the brand icon inline. All styling knobs
(font, font-size, icon size, padding, border-radius, per-state colours) are
exposed through the ``[style]`` global + ``[providers.<id>.style]`` override
sections of config.toml. The installer regenerates this content on every
run, so toggling a provider in config.toml + re-running ``install.sh`` is
the only step the user ever takes.

Usage::

    _generate_waybar.py module --icons-dir DIR --layer-shell-preload PRE
    _generate_waybar.py style  --icons-dir DIR
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # py < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

# Keep DEFAULT_STYLE in sync with coding_plans.config.DEFAULT_CONFIG["style"].
# We duplicate here because this script runs from install.sh without the lib
# package on sys.path.
DEFAULT_STYLE: dict[str, Any] = {
    "font_family":      "",
    "font_size":        "11px",
    "font_weight":      "",
    "letter_spacing":   "0.02em",
    "padding":          "0 8px 0 23px",
    "margin":           "0 3px",
    "icon_size":        "13px",
    "icon_position":    "6px center",
    "border_radius":    "",
    "color":            "@foreground",
    "fresh_opacity":    0.92,
    "stale_opacity":    0.4,
    "empty_opacity":    0.28,
    "critical_color":   "#c9a227",
    "critical_weight":  "700",
    "exhausted_color":  "#d24646",
    "exhausted_weight": "700",
}


def _cfg_path() -> Path:
    cfg_dir = os.environ.get("CFG_DIR_EXPORT") or (
        (os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config"))
        + "/coding-plans"
    )
    return Path(cfg_dir) / "config.toml"


def _load_config() -> dict[str, Any]:
    path = _cfg_path()
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _enabled_providers(cfg: dict[str, Any]) -> list[str]:
    providers = cfg.get("providers") or {}
    return [pid for pid, pcfg in providers.items()
            if isinstance(pcfg, dict) and pcfg.get("enabled")]


def _merged_style(cfg: dict[str, Any], pid: str) -> dict[str, Any]:
    """Global [style] <- [providers.<pid>.style]."""
    merged = dict(DEFAULT_STYLE)
    merged.update(cfg.get("style") or {})
    p_style = (((cfg.get("providers") or {}).get(pid)) or {}).get("style") or {}
    merged.update(p_style)
    return merged


def _icon_filename(pid: str, icons_dir: Path) -> str:
    """Prefer <id>-color.svg over <id>.svg — branded colour SVGs look
    better in the bar than mono shapes against a dark theme."""
    color = icons_dir / f"{pid}-color.svg"
    plain = icons_dir / f"{pid}.svg"
    if color.exists():
        return color.name
    if plain.exists():
        return plain.name
    return plain.name  # missing — the module still renders without the icon


MODULE_TEMPLATE = '''\
"custom/coding-plans-{ID}": {{
  "exec": "coding-plans-bar --provider {ID}",
  "interval": 15,
  "return-type": "json",
  "format": "{{}}",
  "tooltip": true,
  "on-click": "setsid -f env {PRELOAD} coding-plans-popup"
}}'''


def _style_decls(s: dict[str, Any]) -> str:
    """Emit the base rule body (excludes per-state rules)."""
    out: list[str] = []
    if s.get("font_family"):
        out.append(f"  font-family: {s['font_family']};")
    if s.get("font_size"):
        out.append(f"  font-size: {s['font_size']};")
    if s.get("font_weight"):
        out.append(f"  font-weight: {s['font_weight']};")
    if s.get("letter_spacing"):
        out.append(f'  letter-spacing: {s["letter_spacing"]};')
    if s.get("padding"):
        out.append(f"  padding: {s['padding']};")
    if s.get("margin"):
        out.append(f"  margin: {s['margin']};")
    if s.get("border_radius"):
        out.append(f"  border-radius: {s['border_radius']};")
    out.append('  background-repeat: no-repeat;')
    out.append(f'  background-size: {s["icon_size"]} {s["icon_size"]};')
    out.append(f'  background-position: {s["icon_position"]};')
    out.append('  font-feature-settings: "tnum";')
    return "\n".join(out)


def _render_style_for(pid: str, cfg: dict[str, Any], icons_dir: Path) -> str:
    s = _merged_style(cfg, pid)
    icon_path = icons_dir / _icon_filename(pid, icons_dir)
    body = _style_decls(s)
    return f"""\
#custom-coding-plans-{pid} {{
  background-image: url("{icon_path}");
{body}
}}
#custom-coding-plans-{pid}.fresh     {{ color: {s['color']}; opacity: {s['fresh_opacity']}; }}
#custom-coding-plans-{pid}.stale     {{ color: {s['color']}; opacity: {s['stale_opacity']}; }}
#custom-coding-plans-{pid}.critical  {{ color: {s['critical_color']}; font-weight: {s['critical_weight']}; }}
#custom-coding-plans-{pid}.exhausted {{ color: {s['exhausted_color']}; font-weight: {s['exhausted_weight']}; }}
#custom-coding-plans-{pid}.empty     {{ color: {s['color']}; opacity: {s['empty_opacity']}; }}"""


def generate_modules(cfg: dict, preload: str) -> str:
    ids = _enabled_providers(cfg)
    if not ids:
        return ""
    return ",\n".join(MODULE_TEMPLATE.format(ID=pid, PRELOAD=preload) for pid in ids)


def generate_style(cfg: dict, icons_dir: Path) -> str:
    ids = _enabled_providers(cfg)
    if not ids:
        return ""
    return "\n\n".join(_render_style_for(pid, cfg, icons_dir) for pid in ids)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=("module", "style"))
    p.add_argument("--icons-dir", required=True, type=Path)
    p.add_argument("--layer-shell-preload", default="")
    args = p.parse_args(argv)

    cfg = _load_config()
    if args.kind == "module":
        sys.stdout.write(generate_modules(cfg, args.layer_shell_preload))
    else:
        sys.stdout.write(generate_style(cfg, args.icons_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
