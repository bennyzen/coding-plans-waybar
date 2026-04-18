"""Waybar custom-module entry point.

Emits a single JSON object per tick:

    {
      "text":       <Pango label>,
      "tooltip":    <Pango tooltip>,
      "class":      <fresh|stale|critical|exhausted|empty>,
      "alt":        <same as class>,
      "percentage": <0-100, worst across providers>
    }

Iterates ``[providers.*]`` in config, fetches each (failures are caught and
rendered as ``status_class='stale'`` with ``error`` set), and joins per-provider
segments with the configured separator.
"""

from __future__ import annotations

import json
import sys

from .config import load_config
from .formatters import human_ago
from .palette import load_palette
from .providers import load_enabled
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


def _safe_fetch(provider, cfg) -> PlanStatus:
    """Catch anything a provider throws and return a stale PlanStatus with
    ``error`` set. One misbehaving provider must not break the whole bar."""
    try:
        return provider.fetch(cfg)
    except Exception as exc:
        return PlanStatus(
            provider_id=provider.id,
            display_name=provider.display_name,
            icon=provider.icon,
            status_class="stale",
            error=f"fetch failed: {exc!r}",
        )


def main() -> int:
    cfg = load_config()
    palette = load_palette()

    providers = load_enabled(cfg)
    if not providers:
        print(json.dumps(_empty_payload(palette)))
        return 0

    display_cfg = cfg.get("display") or {}
    show_empty = bool(display_cfg.get("show_empty_providers", False))
    join_sep = display_cfg.get("join", "  ")

    plans: list[PlanStatus] = [_safe_fetch(p, cfg) for p in providers]

    # Build bar label per provider.
    label_segments: list[str] = []
    for plan in plans:
        if plan.status_class == "empty" and not show_empty:
            continue
        label_segments.append(render_label(plan, display_cfg))
    label = join_sep.join(label_segments) if label_segments else " —"

    # Build tooltip: one block per provider, dim divider between.
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

    # Footer: UPDATED from the most-recent provider (the ones with state).
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
    # If every provider came back empty or errored, prefer "empty" so the
    # module hints at setup issues (rather than a confusing healthy-looking
    # "stale" class).
    if cls == "stale" and all(p.status_class in {"empty", "stale"} for p in plans):
        if any(p.status_class == "stale" for p in plans):
            cls = "stale"
        else:
            cls = "empty"

    pcts = [p for plan in plans for p in (plan.short_pct, plan.weekly_pct) if p is not None]
    percentage = max(pcts, default=0)

    try:
        print(json.dumps({
            "text": label,
            "tooltip": "\n".join(tooltip_lines),
            "class": cls,
            "alt": cls,
            "percentage": int(percentage),
        }))
    except BrokenPipeError:
        # waybar occasionally closes the pipe mid-write on reload.
        sys.stderr.close()
    return 0
