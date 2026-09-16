"""``formatters.window_pace`` — burn-rate + projection for a rolling window.

Given used-percent, the window's reset epoch and the window length, derive
how much of the window has elapsed, the pace relative to a linear budget,
and the projected utilisation at reset. Pure arithmetic; ``now_s`` is
injected so tests are deterministic.
"""

from __future__ import annotations

from coding_plans.formatters import window_pace

FIVE_H = 5 * 3600
WEEK = 7 * 86400


def test_linear_burn_is_pace_one_and_projects_to_100():
    # Half the window elapsed, half the budget used.
    now = 1_000_000
    resets_at = now + FIVE_H // 2
    pace = window_pace(pct=50, resets_at=resets_at, window_s=FIVE_H, now_s=now)
    assert pace.elapsed_frac == 0.5
    assert pace.ratio == 1.0
    assert pace.projected_pct == 100


def test_fast_burn_projects_over_limit():
    # 25% of window elapsed, 40% used → 1.6× pace → projected 160%.
    now = 1_000_000
    resets_at = now + int(FIVE_H * 0.75)
    pace = window_pace(pct=40, resets_at=resets_at, window_s=FIVE_H, now_s=now)
    assert pace.ratio == 1.6
    assert pace.projected_pct == 160
    assert pace.over is True


def test_slow_burn_is_not_over():
    now = 1_000_000
    resets_at = now + WEEK // 2
    pace = window_pace(pct=20, resets_at=resets_at, window_s=WEEK, now_s=now)
    assert pace.ratio == 0.4
    assert pace.projected_pct == 40
    assert pace.over is False


def test_too_early_in_window_returns_none():
    # <5% of the window elapsed: pace is noise.
    now = 1_000_000
    resets_at = now + FIVE_H - 60
    assert window_pace(pct=3, resets_at=resets_at, window_s=FIVE_H, now_s=now) is None


def test_missing_inputs_return_none():
    now = 1_000_000
    assert window_pace(pct=None, resets_at=now + 100, window_s=FIVE_H, now_s=now) is None
    assert window_pace(pct=10, resets_at=None, window_s=FIVE_H, now_s=now) is None


def test_past_reset_returns_none():
    # Reset already happened; the used-percent is for a window that ended.
    now = 1_000_000
    assert window_pace(pct=10, resets_at=now - 1, window_s=FIVE_H, now_s=now) is None


def test_pace_label_formats_ratio_and_projection():
    from coding_plans.formatters import pace_label

    now = 1_000_000
    pace = window_pace(pct=40, resets_at=now + int(FIVE_H * 0.75), window_s=FIVE_H, now_s=now)
    assert pace_label(pace) == "PACE 1.6× · PROJ 160% · OVER"
    slow = window_pace(pct=20, resets_at=now + WEEK // 2, window_s=WEEK, now_s=now)
    assert pace_label(slow) == "PACE 0.4× · PROJ 40% · OK"
    assert pace_label(None) == "PACE —"


# ─── Per-model rows ────────────────────────────────────────────────────────


def test_model_rows_format_name_tokens_cost_and_share():
    from coding_plans.formatters import model_rows

    rows = model_rows(
        [
            {"model": "opus-5", "tokens": 79_000_000, "cost_usd": 52.40},
            {"model": "opus-4-7", "tokens": 845_000, "cost_usd": 1.73},
        ]
    )
    assert rows == [
        ("OPUS-5", "79.00M", "$52.40", "97%"),
        ("OPUS-4-7", "845.0K", "$1.73", "3%"),
    ]


def test_model_rows_empty_and_zero_cost():
    from coding_plans.formatters import model_rows

    assert model_rows([]) == []
    assert model_rows(None) == []
    # No cost at all → share can't be computed; show a dash, don't divide by zero.
    assert model_rows([{"model": "haiku-4-5", "tokens": 10, "cost_usd": 0}]) == [
        ("HAIKU-4-5", "10", "$0.00", "—")
    ]


def test_pace_label_never_rounds_a_real_burn_to_zero():
    from coding_plans.formatters import pace_label

    now = 1_000_000
    # 1% used with half the window gone → ratio 0.02; "0.0×" would read as idle.
    tiny = window_pace(pct=1, resets_at=now + FIVE_H // 2, window_s=FIVE_H, now_s=now)
    assert pace_label(tiny) == "PACE <0.1× · PROJ 2% · OK"
