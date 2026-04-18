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
