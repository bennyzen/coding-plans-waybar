"""Z.AI (Zhipu GLM Coding Plan) provider.

Stateless: every fetch hits the live quota endpoint::

    GET https://api.z.ai/api/monitor/usage/quota/limit
    Authorization: <raw-api-key>      # NOT "Bearer ..." — just the key

Response shape (captured 2026-04-18, pro plan)::

    {
      "code": 200, "success": true, "msg": "Operation successful",
      "data": {
        "level": "pro",
        "limits": [
          {"type": "TOKENS_LIMIT", "unit": 3, "percentage": 15, "nextResetTime": ...},  # 5h
          {"type": "TOKENS_LIMIT", "unit": 6, "percentage": 32, "nextResetTime": ...},  # 7d
          {"type": "TIME_LIMIT",   "unit": 5, "usage": 1000, "currentValue": 5,
            "remaining": 995, "percentage": 1, "nextResetTime": ..., "usageDetails": [...]}
        ]
      }
    }

Unit mapping (observed; no public docs):
- TOKENS_LIMIT unit=3 → 5-hour rolling window
- TOKENS_LIMIT unit=6 → weekly window
- TIME_LIMIT         → MCP search calls quota (monthly)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .base import PlanStatus

PROVIDER_ID = "zai"
DISPLAY_NAME = "Z.AI"
ICON = ""  # Nerd Font: brain glyph (Zhipu has no official Nerd Font icon)


def _read_key(key_file: str) -> str | None:
    try:
        path = Path(key_file).expanduser()
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _fetch_quota(endpoint: str, key: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(
        endpoint,
        headers={
            "Authorization": key,  # raw key, no Bearer
            "Content-Type": "application/json",
            "User-Agent": "coding-plans-waybar/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _limits_by(limits: list[dict[str, Any]], ltype: str, unit: int | None = None) -> dict[str, Any] | None:
    for lim in limits:
        if lim.get("type") != ltype:
            continue
        if unit is not None and lim.get("unit") != unit:
            continue
        return lim
    return None


def _classify(
    short_pct: int | None,
    weekly_pct: int | None,
    critical: int,
    exhausted: int,
) -> str:
    if short_pct is None and weekly_pct is None:
        return "empty"
    worst = max((p for p in (short_pct, weekly_pct) if p is not None), default=0)
    if worst >= exhausted:
        return "exhausted"
    if worst >= critical:
        return "critical"
    return "fresh"


class ZaiProvider:
    id: str = PROVIDER_ID
    display_name: str = DISPLAY_NAME
    icon: str = ICON

    def fetch(self, config: dict[str, Any]) -> PlanStatus:
        providers = config.get("providers") or {}
        zai_cfg = providers.get(PROVIDER_ID) or {}
        thresholds = config.get("thresholds") or {}
        critical = int(thresholds.get("critical", 80))
        exhausted = int(thresholds.get("exhausted", 100))

        endpoint = zai_cfg.get("endpoint") or "https://api.z.ai/api/monitor/usage/quota/limit"
        key_file = zai_cfg.get("api_key_file") or "~/.config/coding-plans/zai-key"
        timeout = float(zai_cfg.get("timeout") or 6)

        key = _read_key(key_file)
        if not key:
            return PlanStatus(
                provider_id=PROVIDER_ID,
                display_name=DISPLAY_NAME,
                icon=ICON,
                status_class="stale",
                error=f"no api key at {key_file}",
            )

        try:
            payload = _fetch_quota(endpoint, key, timeout)
        except urllib.error.URLError as exc:
            return PlanStatus(
                provider_id=PROVIDER_ID,
                display_name=DISPLAY_NAME,
                icon=ICON,
                status_class="stale",
                error=f"network: {exc.reason}",
            )
        except (json.JSONDecodeError, OSError, TimeoutError) as exc:
            return PlanStatus(
                provider_id=PROVIDER_ID,
                display_name=DISPLAY_NAME,
                icon=ICON,
                status_class="stale",
                error=f"fetch: {exc}",
            )

        if payload.get("code") != 200 or not payload.get("success"):
            msg = str(payload.get("msg") or "unknown error")
            return PlanStatus(
                provider_id=PROVIDER_ID,
                display_name=DISPLAY_NAME,
                icon=ICON,
                status_class="stale",
                error=f"api: {msg}",
            )

        data = payload.get("data") or {}
        limits = data.get("limits") or []
        five_h = _limits_by(limits, "TOKENS_LIMIT", unit=3) or {}
        weekly = _limits_by(limits, "TOKENS_LIMIT", unit=6) or {}
        mcp = _limits_by(limits, "TIME_LIMIT") or {}

        short_pct = five_h.get("percentage")
        weekly_pct = weekly.get("percentage")
        resets_short_ms = five_h.get("nextResetTime")
        resets_weekly_ms = weekly.get("nextResetTime")

        plan_tier = str(data.get("level") or "").strip() or None
        cls = _classify(
            int(short_pct) if short_pct is not None else None,
            int(weekly_pct) if weekly_pct is not None else None,
            critical,
            exhausted,
        )

        return PlanStatus(
            provider_id=PROVIDER_ID,
            display_name=DISPLAY_NAME,
            icon=ICON,
            short_pct=int(short_pct) if short_pct is not None else None,
            weekly_pct=int(weekly_pct) if weekly_pct is not None else None,
            resets_short_ms=int(resets_short_ms) if resets_short_ms else None,
            resets_weekly_ms=int(resets_weekly_ms) if resets_weekly_ms else None,
            plan_tier=plan_tier,
            status_class=cls,
            details={
                "mcp": mcp,
                "level": data.get("level"),
                "raw_limits": limits,
            },
        )


PROVIDER = ZaiProvider()


def tooltip_extras(
    plan: "PlanStatus", cfg: dict[str, Any], palette: dict[str, str]
) -> list[str]:
    """Render the MCP-quota row (Z.AI-specific)."""
    details = plan.details or {}
    mcp = details.get("mcp") or {}
    if not mcp:
        return []

    muted = palette["muted"]
    text = palette["text"]
    current = mcp.get("currentValue") or 0
    total = mcp.get("usage") or 0
    pct = mcp.get("percentage") or 0

    return [
        f"<span foreground='{muted}'>[MCP]</span> "
        f"<span letter_spacing='140' foreground='{text}'>MCP QUOTA</span>"
        f"     <b><span foreground='{text}'>{current}/{total}</span></b>  "
        f"<span foreground='{muted}'>({pct}%)</span>"
    ]
