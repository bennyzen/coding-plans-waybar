"""Claude OAuth usage endpoint → ``providers.claude`` in state.json.

Claude Code's statusLine JSON only ever carries ``five_hour`` and
``seven_day`` (plus a gateway ``spend_limit``). The model-scoped weekly
limits the ``/usage`` dialog shows — "Fable this week" on Max — come from
``GET https://api.anthropic.com/api/oauth/usage``, which the CLI calls with
its own OAuth access token. We make the same read-only call from the
systemd timer so the bar has all three windows even while no Claude Code
turn is running.

Rules that keep this safe:

- Read ``accessToken`` only. Never touch ``refreshToken`` — rotating it
  would log Claude Code out.
- One GET per timer tick, no retries. 401 (token expired because Claude
  Code hasn't run for a while), 429, or network trouble → leave the last
  state in place and exit 0.
- ``main()`` never raises: it runs unattended from a oneshot unit.

Response shape (captured 2026-09-17, Max 20x):

    five_hour / seven_day: {utilization: 0–100, resets_at: ISO-8601}
    limits[]: {kind: "session" | "weekly_all" | "weekly_scoped",
               percent, resets_at, scope: {model: {display_name}, surface}}

The scoped weekly limit lives ONLY in ``limits[]``; the legacy top-level
``seven_day_opus`` / ``seven_day_sonnet`` keys are null on this plan.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from ..formatters import now
from ..state import load_state, provider_state, set_provider_state, write_state

PROVIDER_ID = "claude"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"
DEFAULT_CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
TIMEOUT_S = 10.0


def _pct(x: object) -> int | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return int(round(x))


def _epoch(iso: object) -> int | None:
    if not isinstance(iso, str) or not iso:
        return None
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _window(bucket: object) -> dict[str, Any]:
    if not isinstance(bucket, dict):
        return {"pct": None, "resets_at": None}
    return {"pct": _pct(bucket.get("utilization")), "resets_at": _epoch(bucket.get("resets_at"))}


def _scoped_label(scope: object) -> str | None:
    if not isinstance(scope, dict):
        return None
    for key in ("model", "surface"):
        part = scope.get(key)
        if isinstance(part, dict):
            name = part.get("display_name") or part.get("id")
            if name:
                return str(name)
    return None


def parse_usage(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise the endpoint's JSON into the state-file window shape."""
    scoped: list[dict[str, Any]] = []
    for entry in payload.get("limits") or []:
        if not isinstance(entry, dict) or entry.get("kind") != "weekly_scoped":
            continue
        label = _scoped_label(entry.get("scope"))
        pct = _pct(entry.get("percent"))
        if label is None or pct is None:
            continue
        scoped.append({"label": label, "pct": pct, "resets_at": _epoch(entry.get("resets_at"))})

    return {
        "five_hour": _window(payload.get("five_hour")),
        "seven_day": _window(payload.get("seven_day")),
        "scoped_weekly": scoped,
    }


def record_usage(payload: dict[str, Any]) -> bool:
    """Merge one endpoint response into ``providers.claude``. Returns True
    when something was written."""
    parsed = parse_usage(payload)
    has_window = any(
        parsed[k]["pct"] is not None or parsed[k]["resets_at"] is not None
        for k in ("five_hour", "seven_day")
    )
    if not has_window and not parsed["scoped_weekly"]:
        return False

    from .claude import DEFAULT_SLICE  # local: avoid an import cycle at module load

    state = load_state()
    slice_ = dict(provider_state(state, PROVIDER_ID) or DEFAULT_SLICE)
    for key in ("five_hour", "seven_day"):
        if parsed[key]["pct"] is not None or parsed[key]["resets_at"] is not None:
            slice_[key] = parsed[key]
    slice_["scoped_weekly"] = parsed["scoped_weekly"]
    slice_["updated_at"] = now()
    slice_["source"] = "usage_api"
    set_provider_state(state, PROVIDER_ID, slice_)
    write_state(state)
    return True


def read_access_token(path: Path | None = None) -> str | None:
    target = path or Path(os.environ.get("CLAUDE_CREDENTIALS") or DEFAULT_CREDENTIALS)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
    token = oauth.get("accessToken") if isinstance(oauth, dict) else None
    return str(token) if token else None


def fetch_usage(token: str, timeout: float = TIMEOUT_S) -> dict[str, Any]:
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA,
            "Accept": "application/json",
            "User-Agent": "coding-plans-waybar",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    if not isinstance(payload, dict):
        raise ValueError("usage endpoint returned non-object JSON")
    return payload


def main() -> int:
    token = read_access_token()
    if not token:
        return 0
    try:
        payload = fetch_usage(token)
    except urllib.error.HTTPError as exc:
        # 401 = access token expired (Claude Code refreshes it on its next
        # run); 429 = back off. Either way keep the last good state.
        print(f"coding-plans-usage: HTTP {exc.code}", file=sys.stderr)
        return 0
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"coding-plans-usage: {exc}", file=sys.stderr)
        return 0
    try:
        record_usage(payload)
    except Exception as exc:  # never fail the timer unit over our own bug
        print(f"coding-plans-usage: {exc}", file=sys.stderr)
    return 0
