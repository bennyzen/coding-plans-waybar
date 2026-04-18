"""Pango-markup tooltip rendering — provider-agnostic.

Waybar's tooltip engine renders a narrow subset of Pango (``<span>``, ``<b>``,
``<i>``, ``<small>``, ``<big>``, ``<tt>`` and newlines). No CSS. We lean on
monospace layout and letter_spacing for structure. Aesthetic: IBM-ish
terminal diagnostic — the same look upstream ships.
"""

from __future__ import annotations

import importlib
from typing import Any

from .formatters import human_countdown, reset_wall_clock
from .palette import pct_color
from .providers.base import PlanStatus


CLASS_RANK = {"empty": 0, "fresh": 1, "stale": 2, "critical": 3, "exhausted": 4}


def worst_class(classes: list[str]) -> str:
    """Worst-wins aggregation for per-provider status classes."""
    if not classes:
        return "empty"
    return max(classes, key=lambda c: CLASS_RANK.get(c, 0))


def fmt_pct(pct: int | None) -> str:
    return "?" if pct is None else str(pct)


def bar_string(pct: int | None, width: int) -> str:
    if width <= 0:
        return ""
    if pct is None:
        return "░" * width
    p = max(0, min(100, int(pct)))
    filled = round(p * width / 100)
    return "█" * filled + "░" * (width - filled)


def _brand_name(plan: PlanStatus) -> str:
    """Return ``display_name`` optionally wrapped in a Pango ``<span>`` so the
    provider's brand colour shines in the bar label (e.g. Claude's orange).
    Waybar's text field is Pango, not an image surface — so the bar uses
    the display name as the brand mark; the popup renders the actual SVG."""
    try:
        module = importlib.import_module(f"coding_plans.providers.{plan.provider_id}")
        provider = getattr(module, "PROVIDER", None)
    except ImportError:
        provider = None
    color = getattr(provider, "icon_color", None) if provider else None
    if not color:
        return plan.display_name
    return f"<span foreground='{color}'>{plan.display_name}</span>"


def render_label(plan: PlanStatus, display_cfg: dict[str, Any]) -> str:
    """Format the per-provider bar label using the configured ``bar_format``.

    Placeholders that aren't recognised are treated as empty strings rather
    than raising (helps when a user's config was seeded against an older
    version of DEFAULT_CONFIG and still references dropped placeholders like
    ``{icon}``)."""
    fmt = display_cfg.get("bar_format") or "{short_pct}%·{weekly_pct}%"
    known = {
        "brand":        _brand_name(plan),
        "short_pct":    fmt_pct(plan.short_pct),
        "weekly_pct":   fmt_pct(plan.weekly_pct),
        "plan_tier":    (plan.plan_tier or "").upper(),
        "display_name": plan.display_name,
    }

    class _Silent(dict):
        def __missing__(self, key: str) -> str:  # unknown placeholders stripped
            return ""

    try:
        return fmt.format_map(_Silent(known))
    except (IndexError, ValueError):
        return f"{fmt_pct(plan.short_pct)}%·{fmt_pct(plan.weekly_pct)}%"


def _dim(palette: dict[str, str], s: str) -> str:
    return f"<span foreground='{palette['muted']}'>{s}</span>"


def _strong(color: str, s: str) -> str:
    return f"<b><span foreground='{color}'>{s}</span></b>"


def _metric_block(
    lines: list[str],
    palette: dict[str, str],
    *,
    token: str,
    title: str,
    pct: int | None,
    resets_label: str,
    tooltip_cfg: dict[str, Any],
    critical: int,
    exhausted: int,
) -> None:
    color = pct_color(pct, palette, critical, exhausted)
    head = (
        f"{_dim(palette, f'[{token}]')}  "
        f"<span letter_spacing='140' foreground='{palette['text']}'>{title}</span>"
        f"   {_strong(color, f'{fmt_pct(pct)}%')}"
    )
    lines.append(head)
    if tooltip_cfg.get("show_progress_bars", True):
        bar = bar_string(pct, int(tooltip_cfg.get("bar_width", 10)))
        lines.append(
            f"    <tt><span foreground='{color}'>{bar}</span></tt>"
            f"   {_dim(palette, resets_label.upper())}"
        )
    else:
        lines.append(f"    {_dim(palette, resets_label.upper())}")


def _provider_extras(plan: PlanStatus, cfg: dict[str, Any], palette: dict[str, str]) -> list[str]:
    """Ask the provider's module for extra tooltip lines, if any.

    A provider may expose ``tooltip_extras(plan, cfg, palette) -> list[str]``.
    Missing function → use ``plan.extra_rows`` as a plain "LABEL  VALUE"
    fallback.
    """
    try:
        module = importlib.import_module(f"coding_plans.providers.{plan.provider_id}")
    except ImportError:
        module = None
    fn = getattr(module, "tooltip_extras", None) if module else None
    if callable(fn):
        try:
            return list(fn(plan, cfg, palette))
        except Exception:
            # Extras are optional UI — never let a provider bug kill the
            # tooltip for everyone else.
            return []
    # Default: render extra_rows as simple label/value lines.
    lines: list[str] = []
    for label, value in plan.extra_rows:
        lines.append(
            f"{_dim(palette, f'[{label[:2].upper()}]')}  "
            f"<span letter_spacing='140' foreground='{palette['text']}'>{label.upper()}</span>"
            f"   {_strong(palette['text'], value)}"
        )
    return lines


def render_tooltip_block(
    plan: PlanStatus, cfg: dict[str, Any], palette: dict[str, str]
) -> list[str]:
    """Return the list of Pango lines for one provider's tooltip block."""
    tooltip_cfg = cfg.get("tooltip") or {}
    thresholds = cfg.get("thresholds") or {}
    critical = int(thresholds.get("critical", 80))
    exhausted = int(thresholds.get("exhausted", 100))

    lines: list[str] = []

    # Header: "CLAUDE · USAGE   PLAN: PRO"
    brand = (
        f"<span letter_spacing='440'>{_dim(palette, plan.display_name.upper())}"
        f"  {_dim(palette, '·')}  "
        f"<span foreground='{palette['text']}'>USAGE</span></span>"
    )
    if plan.plan_tier:
        brand += f"   {_dim(palette, f'PLAN: {plan.plan_tier.upper()}')}"
    lines.append(brand)
    lines.append(_dim(palette, "─" * 34))

    short_reset = plan.resets_short_ms // 1000 if plan.resets_short_ms else None
    weekly_reset = plan.resets_weekly_ms // 1000 if plan.resets_weekly_ms else None

    _metric_block(
        lines,
        palette,
        token="5H",
        title="5-HOUR WINDOW",
        pct=plan.short_pct,
        resets_label=f"resets · {human_countdown(short_reset)}",
        tooltip_cfg=tooltip_cfg,
        critical=critical,
        exhausted=exhausted,
    )
    _metric_block(
        lines,
        palette,
        token="7D",
        title="WEEKLY",
        pct=plan.weekly_pct,
        resets_label=f"resets · {reset_wall_clock(weekly_reset)}",
        tooltip_cfg=tooltip_cfg,
        critical=critical,
        exhausted=exhausted,
    )

    lines.extend(_provider_extras(plan, cfg, palette))

    if plan.error:
        lines.append(_dim(palette, f"ERROR: {plan.error.upper()}"))

    return lines
