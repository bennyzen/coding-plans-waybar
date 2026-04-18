"""Claude provider: record_turn → state.json → fetch roundtrip."""

from __future__ import annotations

import importlib
import json


def _reload_claude():
    import coding_plans.providers.claude as mod
    importlib.reload(mod)
    return mod


def test_record_turn_writes_rate_limits(xdg, seeded_claude):
    seeded_claude()
    state_file = xdg["cache"] / "state.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data["schema"] == 2
    claude = data["providers"]["claude"]
    assert claude["five_hour"]["pct"] == 4
    assert claude["seven_day"]["pct"] == 12
    assert claude["session"]["model_name"] == "Opus 4"
    assert claude["updated_at"] > 0


def test_fetch_returns_fresh_plan_status(xdg, seeded_claude):
    seeded_claude()
    mod = _reload_claude()
    plan = mod.PROVIDER.fetch(
        {"thresholds": {"critical": 80, "exhausted": 100}, "behavior": {"stale_after_seconds": 300}}
    )
    assert plan.provider_id == "claude"
    assert plan.short_pct == 4
    assert plan.weekly_pct == 12
    assert plan.status_class == "fresh"
    assert plan.details["session"]["id"] == "s-test"


def test_fetch_empty_when_no_state(xdg):
    mod = _reload_claude()
    plan = mod.PROVIDER.fetch({"thresholds": {"critical": 80, "exhausted": 100}})
    assert plan.short_pct is None
    assert plan.weekly_pct is None
    assert plan.status_class == "empty"


def test_fetch_stale_when_updated_too_old(xdg, seeded_claude):
    seeded_claude()
    mod = _reload_claude()
    # Force an ancient updated_at.
    from coding_plans.state import load_state, write_state, provider_state, set_provider_state
    st = load_state()
    slice_ = dict(provider_state(st, "claude"))
    slice_["updated_at"] = 1  # epoch 1970
    set_provider_state(st, "claude", slice_)
    write_state(st)

    plan = mod.PROVIDER.fetch(
        {"thresholds": {"critical": 80, "exhausted": 100}, "behavior": {"stale_after_seconds": 300}}
    )
    assert plan.status_class == "stale"


def test_fetch_critical_above_threshold(xdg, seeded_claude):
    seeded_claude(rate_limits={
        "five_hour": {"used_percentage": 85, "resets_at": 1776519000},
        "seven_day": {"used_percentage": 30, "resets_at": 1776852000},
    })
    mod = _reload_claude()
    plan = mod.PROVIDER.fetch({"thresholds": {"critical": 80, "exhausted": 100}})
    assert plan.status_class == "critical"


def test_fetch_exhausted_above_threshold(xdg, seeded_claude):
    seeded_claude(rate_limits={
        "five_hour": {"used_percentage": 99, "resets_at": 1776519000},
        "seven_day": {"used_percentage": 101, "resets_at": 1776852000},
    })
    mod = _reload_claude()
    plan = mod.PROVIDER.fetch({"thresholds": {"critical": 80, "exhausted": 100}})
    assert plan.status_class == "exhausted"


def test_record_turn_malformed_json_is_silent(xdg):
    mod = _reload_claude()
    mod.record_turn("not json")
    mod.record_turn("")
    mod.record_turn("[]")  # a list, not a dict — ignored
    # No state should have been written.
    state_file = xdg["cache"] / "state.json"
    assert not state_file.exists()


def test_record_turn_preserves_today_when_statusline_runs(xdg, seeded_claude):
    """ccusage backfill writes .today independently of the statusline; the
    statusline must NOT overwrite it on subsequent turns."""
    seeded_claude()
    # Simulate ccusage backfill writing today.
    from coding_plans.state import load_state, provider_state, set_provider_state, write_state
    st = load_state()
    slice_ = dict(provider_state(st, "claude"))
    slice_["today"] = {"tokens": 12345, "cost_usd": 6.78, "models": ["opus"]}
    set_provider_state(st, "claude", slice_)
    write_state(st)

    # Another statusline turn.
    seeded_claude(rate_limits={
        "five_hour": {"used_percentage": 9, "resets_at": 1776519000},
        "seven_day": {"used_percentage": 18, "resets_at": 1776852000},
    })

    st = load_state()
    assert st["providers"]["claude"]["today"]["tokens"] == 12345
    assert st["providers"]["claude"]["five_hour"]["pct"] == 9
