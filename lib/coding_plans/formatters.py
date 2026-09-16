"""Human-readable formatting helpers.

Ported from upstream claude_usage.py — verbatim, names unchanged.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


def now() -> int:
    return int(time.time())


def human_countdown(target: int | None) -> str:
    if not target:
        return "—"
    delta = target - now()
    if delta <= 0:
        return "now"
    if delta < 3600:
        return f"{delta // 60}m"
    hours, rem = divmod(delta, 3600)
    minutes = rem // 60
    if hours < 24:
        return f"{hours}h {minutes:02d}m"
    days = hours // 24
    return f"{days}d {hours % 24}h"


def human_ago(ts: int) -> str:
    if not ts:
        return "never"
    delta = now() - ts
    if delta < 5:
        return "just now"
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        hours, rem = divmod(delta, 3600)
        return f"{hours}h {rem // 60}m ago"
    return f"{delta // 86400}d ago"


def human_tokens(n: int | float) -> str:
    if not n:
        return "0"
    if n < 1000:
        return str(int(n))
    if n < 1_000_000:
        return f"{n / 1000:.1f}K"
    if n < 1_000_000_000:
        return f"{n / 1_000_000:.2f}M"
    return f"{n / 1_000_000_000:.2f}B"


def human_cost(usd: float | int | None) -> str:
    if not usd:
        return "$0.00"
    if usd < 100:
        return f"${usd:.2f}"
    return f"${usd:,.0f}"


def human_duration(ms: int | None) -> str:
    if not ms:
        return "0s"
    s = ms / 1000
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        return f"{int(s // 60)}m {int(s % 60)}s"
    h, rem = divmod(int(s), 3600)
    return f"{h}h {rem // 60}m"


def reset_wall_clock(target: int | None) -> str:
    """Render an epoch timestamp as 'Mon 2:59 PM' for the weekly reset."""
    if not target:
        return "—"
    tm = time.localtime(target)
    return time.strftime("%a %-I:%M %p", tm)


def is_stale(updated_at: int, limit_seconds: int = 300) -> bool:
    """Check if a ``updated_at`` epoch-seconds timestamp is older than ``limit``."""
    if not updated_at:
        return True
    return (now() - updated_at) > limit_seconds


# ─── Pace / pressure ───────────────────────────────────────────────────────

# Below this share of the window, a handful of requests skew the ratio
# wildly (2% used in the first minute reads as "60× pace"). Show nothing.
PACE_MIN_ELAPSED_FRAC = 0.05

# Window lengths shared by every provider so far: a rolling 5-hour bucket and
# a 7-day bucket (Claude's five_hour/seven_day, Z.AI's unit=3/unit=6).
SHORT_WINDOW_S = 5 * 3600
WEEKLY_WINDOW_S = 7 * 86400


@dataclass(frozen=True)
class WindowPace:
    """Burn rate for one rolling quota window.

    ``elapsed_frac`` — share of the window already gone, 0–1.
    ``ratio``        — used share ÷ elapsed share. 1.0 is a linear burn.
    ``projected_pct``— utilisation at reset if the ratio holds.
    ``over``         — projection crosses 100 %.
    """

    elapsed_frac: float
    ratio: float
    projected_pct: int

    @property
    def over(self) -> bool:
        return self.projected_pct > 100


def window_pace(
    *,
    pct: int | float | None,
    resets_at: int | None,
    window_s: int,
    now_s: int | None = None,
) -> WindowPace | None:
    """Derive pace + projection from a window's used-percent and reset epoch.

    Returns ``None`` when the inputs are missing, the reset is in the past,
    or too little of the window has elapsed for the ratio to mean anything.
    """
    if pct is None or not resets_at or window_s <= 0:
        return None
    current = now() if now_s is None else now_s
    remaining = resets_at - current
    if remaining <= 0 or remaining > window_s:
        return None
    elapsed_frac = (window_s - remaining) / window_s
    if elapsed_frac < PACE_MIN_ELAPSED_FRAC:
        return None
    ratio = (pct / 100.0) / elapsed_frac
    return WindowPace(
        elapsed_frac=round(elapsed_frac, 4),
        ratio=round(ratio, 2),
        projected_pct=int(round(ratio * 100)),
    )


def pace_label(pace: WindowPace | None) -> str:
    """One-line popup/tooltip rendering: ``PACE 1.6× · PROJ 160% · OVER``."""
    if pace is None:
        return "PACE —"
    tag = "OVER" if pace.over else "OK"
    # A real-but-slow burn must not read as idle: 0.03 becomes "<0.1", not "0.0".
    ratio = f"{pace.ratio:.1f}" if pace.ratio >= 0.1 else "<0.1"
    return f"PACE {ratio}× · PROJ {pace.projected_pct}% · {tag}"


# ─── Per-model breakdown ───────────────────────────────────────────────────


def model_rows(by_model: list[dict] | None) -> list[tuple[str, str, str, str]]:
    """Turn ``today.by_model`` entries into display tuples:
    ``(NAME, tokens, cost, share-of-cost)``. Share is a dash when the day
    has no cost yet (avoids a divide-by-zero on a fresh day).
    """
    if not by_model:
        return []
    total_cost = sum(float(m.get("cost_usd") or 0) for m in by_model)
    rows: list[tuple[str, str, str, str]] = []
    for m in by_model:
        cost = float(m.get("cost_usd") or 0)
        share = f"{round(cost / total_cost * 100)}%" if total_cost > 0 else "—"
        rows.append(
            (
                str(m.get("model") or "?").upper(),
                human_tokens(m.get("tokens") or 0),
                human_cost(cost),
                share,
            )
        )
    return rows
