"""Waybar custom-module entry point.

Two modes:

- ``coding-plans-bar``                     render every enabled provider,
                                           joined with the configured
                                           separator (single-module layout).
- ``coding-plans-bar --provider <id>``     render just that one provider —
                                           used when a Waybar config has one
                                           ``custom/coding-plans-<id>`` per
                                           provider (default since v0.2,
                                           each provider's SVG sits in its
                                           own module via CSS background-image).

Output schema per tick::

    {
      "text":       <Pango label>,
      "tooltip":    <Pango tooltip>,
      "class":      <fresh|stale|critical|exhausted|empty>,
      "alt":        <same as class>,
      "percentage": <0-100, worst across providers>
    }
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys

from .config import load_config
from .formatters import human_ago
from .palette import load_palette
from .providers import load_enabled, safe_fetch
from .providers.base import PlanStatus
from .render import render_label, render_tooltip_block, worst_class


def _empty_payload(palette: dict[str, str]) -> dict:
    muted = palette["muted"]
    tooltip = (
        f"<span letter_spacing='440' foreground='{muted}'>CODING PLANS  ·  USAGE</span>\n"
        f"<span foreground='{muted}'>─ ─ ─ ─ ─ ─ ─ ─</span>\n"
        f"<small><span foreground='{muted}'>NO PROVIDERS ENABLED — "
        f"edit ~/.config/coding-plans/config.toml</span></small>"
    )
    return {
        "text": " —",
        "tooltip": tooltip,
        "class": "empty",
        "alt": "empty",
        "percentage": 0,
    }


def _render(plans: list[PlanStatus], cfg: dict, palette: dict) -> dict:
    """Shared rendering for both single-provider and multi-provider modes."""
    display_cfg = cfg.get("display") or {}
    show_empty = bool(display_cfg.get("show_empty_providers", False))
    join_sep = display_cfg.get("join", "  ")

    # Bar label.
    label_segments: list[str] = []
    for plan in plans:
        if plan.status_class == "empty" and not show_empty:
            continue
        label_segments.append(render_label(plan, display_cfg))
    label = join_sep.join(label_segments) if label_segments else "—"

    # Tooltip: one block per provider, dim divider between.
    tooltip_parts: list[list[str]] = [
        render_tooltip_block(plan, cfg, palette) for plan in plans
    ]
    muted = palette["muted"]
    divider = f"<span foreground='{muted}'>─ ─ ─ ─ ─ ─ ─ ─</span>"
    tooltip_lines: list[str] = []
    for i, block in enumerate(tooltip_parts):
        if i > 0:
            tooltip_lines.append(divider)
        tooltip_lines.extend(block)

    if (cfg.get("tooltip") or {}).get("show_updated_ago", True):
        updated = max(
            (int((p.details or {}).get("updated_at") or 0) for p in plans),
            default=0,
        )
        if updated:
            suffix = ""
            stale_limit = int((cfg.get("behavior") or {}).get("stale_after_seconds", 300))
            from .formatters import is_stale
            if is_stale(updated, stale_limit):
                suffix = " · IDLE"
            tooltip_lines.append(f"<span foreground='{muted}'>{'─' * 34}</span>")
            tooltip_lines.append(
                f"<span foreground='{muted}'>UPDATED {human_ago(updated).upper()}{suffix}</span>"
            )

    cls = worst_class([p.status_class for p in plans])

    pcts = [p for plan in plans for p in (plan.short_pct, plan.weekly_pct) if p is not None]
    percentage = max(pcts, default=0)

    return {
        "text": label,
        "tooltip": "\n".join(tooltip_lines),
        "class": cls,
        "alt": cls,
        "percentage": int(percentage),
    }


def _emit(payload: dict) -> None:
    """Print one Waybar JSON payload. Swallows BrokenPipeError — waybar
    occasionally closes the pipe mid-write on reload, and the resulting
    traceback on stderr is noise. Affects every emit path equally
    (single-provider, multi-provider, and the two empty states)."""
    try:
        print(json.dumps(payload))
    except BrokenPipeError:
        sys.stderr.close()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="coding-plans-bar",
        description="Render Waybar JSON for one or all enabled providers.",
    )
    parser.add_argument(
        "--provider",
        help="Render only this provider id (e.g. 'claude'). "
             "Used in the per-provider module layout (one Waybar module per provider).",
        default=None,
    )
    return parser.parse_args(argv)


def _load_single_provider(pid: str, cfg: dict):
    """Import ``coding_plans.providers.<pid>`` and return its ``PROVIDER``.
    Returns None if the provider isn't enabled or the module doesn't exist."""
    pcfg = (cfg.get("providers") or {}).get(pid) or {}
    if not pcfg.get("enabled", False):
        return None
    try:
        module = importlib.import_module(f"coding_plans.providers.{pid}")
    except ImportError:
        return None
    return getattr(module, "PROVIDER", None)


def main(argv: list[str] | None = None) -> int:
    # argv=None at runtime means "use sys.argv[1:]"; tests pass [] to avoid
    # inheriting pytest's own flags.
    if argv is None:
        argv = sys.argv[1:]
    args = _parse_args(argv)
    cfg = load_config()
    palette = load_palette()

    # Single-provider mode (the per-module layout).
    if args.provider:
        provider = _load_single_provider(args.provider, cfg)
        if provider is None:
            # Emit a visible empty segment so the user can see the module is
            # alive but unconfigured.
            _emit({
                "text": "—",
                "tooltip": f"provider '{args.provider}' not enabled in ~/.config/coding-plans/config.toml",
                "class": "empty",
                "alt": "empty",
                "percentage": 0,
            })
            return 0
        plans = [safe_fetch(provider, cfg)]
        _emit(_render(plans, cfg, palette))
        return 0

    # Multi-provider mode (legacy single-module layout).
    providers = load_enabled(cfg)
    if not providers:
        _emit(_empty_payload(palette))
        return 0
    plans = [safe_fetch(p, cfg) for p in providers]
    _emit(_render(plans, cfg, palette))
    return 0
