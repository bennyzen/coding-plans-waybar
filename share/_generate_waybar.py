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
import re
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
    "icon_bg_color":    "",      # "" = no backdrop
    "icon_bg_padding":  "2px",
    "border_radius":    "",
    "color":            "@foreground",
    "fresh_opacity":    1.0,
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


def _parse_pos(icon_position: str) -> tuple[str, str]:
    """Split e.g. '6px center' → ('6px', 'center')."""
    parts = (icon_position or "").strip().split()
    x = parts[0] if len(parts) > 0 else "0"
    y = parts[1] if len(parts) > 1 else "center"
    return x, y


def _color_slug(color: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in color).strip("_") or "bg"


def _write_disc_svg(icons_dir: Path, color: str) -> Path:
    """Emit a razor-sharp filled circle SVG, cached by colour slug.

    A 24×24 viewBox (matches the brand SVGs LobeHub ships) and explicit
    width/height keep librsvg's rasteriser happy; unit-less tiny
    viewBoxes can render as mush at small background-sizes.
    """
    path = icons_dir / f"disc-{_color_slug(color)}.svg"
    if not path.exists():
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' "
            "width='24' height='24' viewBox='0 0 24 24'>"
            f"<circle cx='12' cy='12' r='12' fill='{color}'/></svg>"
        )
        path.write_text(svg, encoding="utf-8")
    return path


_PX_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*px\s*$")


def _as_px(value: str) -> float | None:
    m = _PX_RE.match(value or "")
    return float(m.group(1)) if m else None


def _fmt_px(n: float) -> str:
    return f"{int(n)}px" if n == int(n) else f"{n}px"


def _background_lines(
    s: dict[str, Any], icon_path: Path, disc_path: Path | None
) -> list[str]:
    """Emit the ``background-*`` properties.

    When ``disc_path`` is set, layer a solid SVG disc behind the brand
    icon. Disc diameter = ``icon_size + 2 * icon_bg_padding``, positioned
    so its centre aligns with the icon's centre.
    """
    icon_size = s["icon_size"]
    icon_pos = s["icon_position"]

    if disc_path is None:
        return [
            f'  background-image: url("{icon_path}");',
            f'  background-size: {icon_size} {icon_size};',
            f'  background-position: {icon_pos};',
            '  background-repeat: no-repeat;',
        ]

    padding = s.get("icon_bg_padding") or "0px"
    icon_x, icon_y = _parse_pos(icon_pos)
    # Prefer literal px arithmetic over calc(): GTK4 CSS handles calc(),
    # but a few stacks choke on calc inside a multi-value background-size
    # and silently fall back to ``auto`` — which blows the disc up to
    # cover the whole module. Precomputing dodges the whole risk.
    isz = _as_px(icon_size)
    pad = _as_px(padding)
    ix = _as_px(icon_x)
    if isz is not None and pad is not None:
        disc_size = _fmt_px(isz + 2 * pad)
    else:
        disc_size = f"calc({icon_size} + 2 * {padding})"
    if ix is not None and pad is not None:
        disc_x = _fmt_px(ix - pad)
    else:
        disc_x = f"calc({icon_x} - {padding})"
    return [
        f'  background-image: url("{icon_path}"), url("{disc_path}");',
        f'  background-size: {icon_size} {icon_size}, {disc_size} {disc_size};',
        f'  background-position: {icon_pos}, {disc_x} {icon_y};',
        '  background-repeat: no-repeat, no-repeat;',
    ]


def _style_decls(
    s: dict[str, Any], icon_path: Path, disc_path: Path | None
) -> str:
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
    out.extend(_background_lines(s, icon_path, disc_path))
    out.append('  font-feature-settings: "tnum";')
    return "\n".join(out)


def _render_style_for(pid: str, cfg: dict[str, Any], icons_dir: Path) -> str:
    s = _merged_style(cfg, pid)
    icon_path = icons_dir / _icon_filename(pid, icons_dir)
    bg_color = (s.get("icon_bg_color") or "").strip()
    disc_path = _write_disc_svg(icons_dir, bg_color) if bg_color else None
    body = _style_decls(s, icon_path, disc_path)
    return f"""\
#custom-coding-plans-{pid} {{
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
