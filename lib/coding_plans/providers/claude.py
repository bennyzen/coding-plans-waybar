"""Claude provider.

Reads the Claude slice of ``~/.cache/coding-plans/state.json`` that
``coding-plans-statusline`` (every Claude Code turn) and
``coding-plans-today`` (every 5 minutes from the systemd timer) populate.

The fetch side is straight lookup → ``PlanStatus``. The module also exports
statusline-side helpers (``extract_rate_limits``, ``extract_session``,
``record_turn``) used by ``coding_plans.statusline``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..formatters import is_stale, now
from ..state import load_state, provider_state, set_provider_state, write_state
from .base import PlanStatus

PROVIDER_ID = "claude"
DISPLAY_NAME = "Claude"
# Brand icon. Ships alongside this module at providers/icons/<id>.svg,
# source: @lobehub/icons-static-svg (MIT). The bar label uses display_name
# (text — Pango in Waybar can't inline SVGs); the popup renders the SVG
# directly. Brand orange from Anthropic's site.
ICON_PATH = Path(__file__).parent / "icons" / "claude-color.svg"
ICON_COLOR = "#D97757"

DEFAULT_SLICE: dict[str, Any] = {
    "five_hour": {"pct": None, "resets_at": None},
    "seven_day": {"pct": None, "resets_at": None},
    "today": {"tokens": 0, "cost_usd": 0.0, "models": []},
    "session": {
        "id": "",
        "model_id": "",
        "model_name": "",
        "cost_usd": 0.0,
        "lines_added": 0,
        "lines_removed": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "context_pct": None,
    },
    "updated_at": 0,
    "source": "none",
}


def _classify(
    short_pct: int | None,
    weekly_pct: int | None,
    stale: bool,
    critical: int,
    exhausted: int,
) -> str:
    if short_pct is None and weekly_pct is None:
        return "empty"
    if stale:
        return "stale"
    worst = max((p for p in (short_pct, weekly_pct) if p is not None), default=0)
    if worst >= exhausted:
        return "exhausted"
    if worst >= critical:
        return "critical"
    return "fresh"


class ClaudeProvider:
    id: str = PROVIDER_ID
    display_name: str = DISPLAY_NAME
    icon_path: Path = ICON_PATH
    icon_color: str | None = ICON_COLOR

    def fetch(self, config: dict[str, Any]) -> PlanStatus:
        behavior = config.get("behavior") or {}
        thresholds = config.get("thresholds") or {}
        critical = int(thresholds.get("critical", 80))
        exhausted = int(thresholds.get("exhausted", 100))
        stale_limit = int(behavior.get("stale_after_seconds", 300))

        state = load_state()
        slice_ = provider_state(state, PROVIDER_ID) or DEFAULT_SLICE

        five = slice_.get("five_hour") or {}
        seven = slice_.get("seven_day") or {}
        updated_at = int(slice_.get("updated_at") or 0)

        short_pct = five.get("pct")
        weekly_pct = seven.get("pct")
        resets_short = five.get("resets_at")
        resets_weekly = seven.get("resets_at")

        stale = is_stale(updated_at, stale_limit)
        cls = _classify(short_pct, weekly_pct, stale, critical, exhausted)

        return PlanStatus(
            provider_id=PROVIDER_ID,
            display_name=DISPLAY_NAME,
            short_pct=short_pct,
            weekly_pct=weekly_pct,
            resets_short_ms=int(resets_short) * 1000 if resets_short else None,
            resets_weekly_ms=int(resets_weekly) * 1000 if resets_weekly else None,
            plan_tier=None,  # Claude's rate_limits don't expose tier
            status_class=cls,
            details=dict(slice_),
        )


PROVIDER = ClaudeProvider()


def tooltip_extras(
    plan: "PlanStatus", cfg: dict[str, Any], palette: dict[str, str]
) -> list[str]:
    """Render upstream's TODAY + SESSION rows from the raw Claude state
    slice in ``plan.details``. Returns Pango-markup lines.
    """
    from ..formatters import human_cost, human_tokens

    details = plan.details or {}
    tcfg = cfg.get("tooltip") or {}
    muted = palette["muted"]
    text = palette["text"]
    lines: list[str] = []

    def dim(s: str) -> str:
        return f"<span foreground='{muted}'>{s}</span>"

    def strong(s: str, color: str) -> str:
        return f"<b><span foreground='{color}'>{s}</span></b>"

    if tcfg.get("show_today", True):
        today = details.get("today") or {}
        tokens = human_tokens(today.get("tokens", 0) or 0)
        cost = human_cost(today.get("cost_usd", 0) or 0)
        lines.append(
            f"{dim('[TD]')}  "
            f"<span letter_spacing='140' foreground='{text}'>TODAY</span>"
            f"           {strong(tokens, text)} {dim('TOK')}  "
            f"{strong(cost, text)}"
        )

    session = details.get("session") or {}
    if session.get("id"):
        ctx_pct = session.get("context_pct")
        ctx_str = "—" if ctx_pct is None else f"{ctx_pct}%"
        sess_cost = human_cost(session.get("cost_usd", 0) or 0)
        added = session.get("lines_added", 0) or 0
        removed = session.get("lines_removed", 0) or 0
        lines.append(
            f"{dim('[SS]')}  "
            f"<span letter_spacing='140' foreground='{text}'>SESSION</span>"
            f"         {strong(sess_cost, text)}  "
            f"{dim('CTX')} {strong(ctx_str, text)}  "
            f"{dim('±')} {strong(f'+{added}/-{removed}', text)}"
        )

    return lines


# ─── Statusline-side helpers ──────────────────────────────────────────────


def _int(x: object) -> int | None:
    return int(x) if isinstance(x, (int, float)) else None


def extract_rate_limits(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pull five_hour / seven_day from rate_limits. Real keys only — Claude
    Code has never shipped `weekly`, `reset_at`, etc."""
    rl = data.get("rate_limits") or {}
    five = rl.get("five_hour") or {}
    week = rl.get("seven_day") or {}

    def norm(bucket: dict[str, Any]) -> dict[str, Any]:
        return {
            "pct": _int(bucket.get("used_percentage")),
            "resets_at": _int(bucket.get("resets_at")),
        }

    return norm(five), norm(week)


def extract_session(data: dict[str, Any]) -> dict[str, Any]:
    """Pull the per-session fields the UI surfaces.

    Schema pinned against captured v2.1.108 stdin. We deliberately store
    only what the bar/popup renders — adding a field here is a promise to
    display it somewhere.
    """
    model = data.get("model") or {}
    cost = data.get("cost") or {}
    ctx = data.get("context_window") or {}

    return {
        "id": str(data.get("session_id") or ""),
        "model_id": str(model.get("id") or ""),
        "model_name": str(model.get("display_name") or model.get("id") or ""),
        "cost_usd": float(cost.get("total_cost_usd") or 0),
        "lines_added": int(cost.get("total_lines_added") or 0),
        "lines_removed": int(cost.get("total_lines_removed") or 0),
        "input_tokens": int(ctx.get("total_input_tokens") or 0),
        "output_tokens": int(ctx.get("total_output_tokens") or 0),
        "context_pct": _int(ctx.get("used_percentage")),
    }


def build_popup_rows(
    plan: "PlanStatus", cfg: dict[str, Any], palette: dict[str, str]
) -> list[Any]:
    """Return the GTK4 widgets the popup should render AFTER the shared
    5H/WEEKLY rows. For Claude: a TodayRow + a SessionRow, both populated
    from ``plan.details`` (the full state-file slice).

    Imported lazily inside the function body — the statusline and bar
    modules also import from this file and must not pull in PyGObject.
    """
    from ..popup import SessionRow, TodayRow  # noqa: WPS433 — intentional

    del cfg, palette  # shared styling is applied via CSS on the widgets.
    return [TodayRow(), SessionRow()]


def record_turn(raw: str) -> None:
    """Parse one Claude Code statusline-JSON payload and merge it into
    ``~/.cache/coding-plans/state.json`` under ``providers.claude``.

    Silent on malformed input — statusline is a hot path and breaking
    Claude Code's UI over our own bug is worse than a missed update.
    """
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return

    five, week = extract_rate_limits(data)
    session = extract_session(data)

    has_rate = (
        five["pct"] is not None
        or five["resets_at"] is not None
        or week["pct"] is not None
        or week["resets_at"] is not None
    )
    has_session = bool(session["id"])
    if not has_rate and not has_session:
        # Claude Code piped stdin but no fields the UI cares about — don't
        # touch state.json (keeps "stale" detection honest and avoids
        # rewriting the file every silent turn).
        return

    state = load_state()
    slice_ = dict(provider_state(state, PROVIDER_ID) or DEFAULT_SLICE)
    # Only overwrite rate-limit fields when Claude Code actually gives them.
    if five["pct"] is not None or five["resets_at"] is not None:
        slice_["five_hour"] = five
    if week["pct"] is not None or week["resets_at"] is not None:
        slice_["seven_day"] = week
    if session["id"]:
        slice_["session"] = session
    slice_["updated_at"] = now()
    slice_["source"] = "statusline"

    set_provider_state(state, PROVIDER_ID, slice_)
    write_state(state)
