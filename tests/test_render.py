"""Renderer helpers: worst_class aggregation + bar_string edge cases."""

from __future__ import annotations

from coding_plans.render import bar_string, worst_class, fmt_pct


def test_worst_class_aggregation():
    assert worst_class(["fresh"]) == "fresh"
    assert worst_class(["fresh", "stale"]) == "stale"
    assert worst_class(["fresh", "critical"]) == "critical"
    assert worst_class(["fresh", "exhausted"]) == "exhausted"
    assert worst_class(["stale", "exhausted"]) == "exhausted"
    assert worst_class(["empty", "empty"]) == "empty"
    assert worst_class([]) == "empty"


def test_bar_string_full_and_empty():
    assert bar_string(0, 10) == "░" * 10
    assert bar_string(100, 10) == "█" * 10
    assert bar_string(None, 10) == "░" * 10
    assert bar_string(50, 10) == "█" * 5 + "░" * 5


def test_bar_string_zero_width():
    assert bar_string(50, 0) == ""
    assert bar_string(None, 0) == ""


def test_fmt_pct():
    assert fmt_pct(0) == "0"
    assert fmt_pct(100) == "100"
    assert fmt_pct(None) == "?"


# ─── scoped weekly windows ─────────────────────────────────────────────────


def _plan_with_scoped(pct=13):
    from coding_plans.providers.base import PlanStatus, ScopedWindow

    return PlanStatus(
        provider_id="claude",
        display_name="Claude",
        short_pct=1,
        weekly_pct=23,
        resets_short_ms=1776519000 * 1000,
        resets_weekly_ms=1776852000 * 1000,
        status_class="fresh",
        scoped_weekly=[ScopedWindow(label="Fable", pct=pct, resets_ms=1776852000 * 1000)],
    )


def test_render_label_scoped_pct_placeholder():
    from coding_plans.render import render_label
    from coding_plans.providers.base import PlanStatus

    plan = _plan_with_scoped()
    assert render_label(plan, {"bar_format": "{weekly_pct}%·{scoped_pct}%"}) == "23%·13%"
    bare = PlanStatus(provider_id="zai", display_name="Z.AI", weekly_pct=5, status_class="fresh")
    assert render_label(bare, {"bar_format": "{weekly_pct}%·{scoped_pct}%"}) == "5%·?%"


def test_tooltip_lists_scoped_weekly_block():
    from coding_plans.render import render_tooltip_block
    from coding_plans.palette import BAKED_PALETTE

    lines = render_tooltip_block(_plan_with_scoped(), {"tooltip": {}, "thresholds": {}}, dict(BAKED_PALETTE))
    joined = "\n".join(lines)
    assert "FABLE WEEKLY" in joined
    assert joined.index("WEEKLY") < joined.index("FABLE WEEKLY")
