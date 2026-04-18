"""Human-readable formatting helpers.

Ported from upstream claude_usage.py — verbatim, names unchanged.
"""

from __future__ import annotations

import time


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
