"""Claude OAuth usage endpoint: parse → state.json merge → error handling.

Fixture mirrors a real ``GET /api/oauth/usage`` response captured 2026-09-17
(Max 20x, Fable weekly limit active). The model-scoped weekly limit only
appears in ``limits[]`` — the legacy ``seven_day_opus``-style keys are null.
"""

from __future__ import annotations

import importlib
import io
import json
import urllib.error
from unittest.mock import patch


def _reload():
    import coding_plans.providers.claude_usage_api as mod

    importlib.reload(mod)
    return mod


def _payload(**overrides):
    body = {
        "five_hour": {"utilization": 1.0, "resets_at": "2026-09-17T17:20:00.377707+00:00"},
        "seven_day": {"utilization": 23.0, "resets_at": "2026-09-20T07:00:00.377727+00:00"},
        "seven_day_opus": None,
        "limits": [
            {
                "kind": "session",
                "group": "session",
                "percent": 1,
                "resets_at": "2026-09-17T17:20:00.377707+00:00",
                "scope": None,
            },
            {
                "kind": "weekly_all",
                "group": "weekly",
                "percent": 23,
                "resets_at": "2026-09-20T07:00:00.377727+00:00",
                "scope": None,
            },
            {
                "kind": "weekly_scoped",
                "group": "weekly",
                "percent": 13,
                "resets_at": "2026-09-20T07:00:00.377964+00:00",
                "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None},
            },
        ],
    }
    body.update(overrides)
    return body


FIVE_RESET = 1789665600  # 2026-09-17T17:20:00Z
WEEK_RESET = 1789887600  # 2026-09-20T07:00:00Z


# ─── parse_usage ───────────────────────────────────────────────────────────


def test_parse_usage_extracts_windows_as_epoch_seconds():
    mod = _reload()
    parsed = mod.parse_usage(_payload())
    assert parsed["five_hour"] == {"pct": 1, "resets_at": FIVE_RESET}
    assert parsed["seven_day"] == {"pct": 23, "resets_at": WEEK_RESET}


def test_parse_usage_extracts_scoped_weekly_limits():
    mod = _reload()
    parsed = mod.parse_usage(_payload())
    assert parsed["scoped_weekly"] == [
        {"label": "Fable", "pct": 13, "resets_at": WEEK_RESET}
    ]


def test_parse_usage_scoped_label_falls_back_to_surface():
    mod = _reload()
    limits = _payload()["limits"]
    limits.append(
        {
            "kind": "weekly_scoped",
            "group": "weekly",
            "percent": 40,
            "resets_at": "2026-09-20T07:00:00+00:00",
            "scope": {"model": None, "surface": {"display_name": "Cowork"}},
        }
    )
    parsed = mod.parse_usage(_payload(limits=limits))
    assert [w["label"] for w in parsed["scoped_weekly"]] == ["Fable", "Cowork"]


def test_parse_usage_tolerates_missing_fields():
    mod = _reload()
    parsed = mod.parse_usage({"five_hour": None, "limits": None})
    assert parsed["five_hour"] == {"pct": None, "resets_at": None}
    assert parsed["seven_day"] == {"pct": None, "resets_at": None}
    assert parsed["scoped_weekly"] == []


# ─── record_usage ─────────────────────────────────────────────────────────


def test_record_usage_merges_into_claude_slice(xdg, seeded_claude):
    seeded_claude()  # statusline wrote session + older rate limits
    mod = _reload()
    mod.record_usage(_payload())

    data = json.loads((xdg["cache"] / "state.json").read_text())
    claude = data["providers"]["claude"]
    assert claude["five_hour"] == {"pct": 1, "resets_at": FIVE_RESET}
    assert claude["seven_day"] == {"pct": 23, "resets_at": WEEK_RESET}
    assert claude["scoped_weekly"] == [{"label": "Fable", "pct": 13, "resets_at": WEEK_RESET}]
    assert claude["source"] == "usage_api"
    assert claude["updated_at"] > 0
    # Session data written by the statusline survives.
    assert claude["session"]["id"] == "s-test"


def test_record_usage_without_any_window_leaves_state_alone(xdg):
    mod = _reload()
    mod.record_usage({"limits": []})
    assert not (xdg["cache"] / "state.json").exists()


# ─── credentials ──────────────────────────────────────────────────────────


def test_read_access_token(tmp_path):
    mod = _reload()
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat01-x"}}))
    assert mod.read_access_token(creds) == "sk-ant-oat01-x"


def test_read_access_token_missing_or_malformed(tmp_path):
    mod = _reload()
    assert mod.read_access_token(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert mod.read_access_token(bad) is None


# ─── main() ───────────────────────────────────────────────────────────────


def test_main_fetches_and_records(xdg, tmp_path, monkeypatch):
    mod = _reload()
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "tok"}}))
    monkeypatch.setenv("CLAUDE_CREDENTIALS", str(creds))

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["auth"] = req.get_header("Authorization")
        captured["beta"] = req.get_header("Anthropic-beta")
        return _Resp(json.dumps(_payload()).encode())

    with patch.object(mod.urllib.request, "urlopen", fake_urlopen):
        assert mod.main() == 0

    assert captured["auth"] == "Bearer tok"
    assert captured["beta"] == "oauth-2025-04-20"
    claude = json.loads((xdg["cache"] / "state.json").read_text())["providers"]["claude"]
    assert claude["scoped_weekly"][0]["label"] == "Fable"


def test_main_http_error_leaves_state_untouched(xdg, tmp_path, monkeypatch):
    mod = _reload()
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "expired"}}))
    monkeypatch.setenv("CLAUDE_CREDENTIALS", str(creds))

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

    with patch.object(mod.urllib.request, "urlopen", boom):
        assert mod.main() == 0
    assert not (xdg["cache"] / "state.json").exists()


def test_main_without_credentials_is_a_noop(xdg, tmp_path, monkeypatch):
    mod = _reload()
    monkeypatch.setenv("CLAUDE_CREDENTIALS", str(tmp_path / "missing.json"))
    with patch.object(mod.urllib.request, "urlopen", side_effect=AssertionError("must not call")):
        assert mod.main() == 0
    assert not (xdg["cache"] / "state.json").exists()
