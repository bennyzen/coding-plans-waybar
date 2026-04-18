"""Z.AI provider: HTTP fetch + error paths."""

from __future__ import annotations

import importlib
import json
from io import BytesIO
from unittest.mock import patch


def _reload_zai():
    import coding_plans.providers.zai as mod
    importlib.reload(mod)
    return mod


def _mock_response(payload: dict):
    class _Resp:
        def __init__(self, data):
            self._data = data
        def read(self):
            return json.dumps(self._data).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    return _Resp(payload)


def test_fetch_parses_pro_plan(tmp_path):
    mod = _reload_zai()
    key_file = tmp_path / "zai-key"
    key_file.write_text("FAKE-KEY-123\n")

    payload = {
        "code": 200, "success": True, "msg": "ok",
        "data": {
            "level": "pro",
            "limits": [
                {"type": "TOKENS_LIMIT", "unit": 3, "percentage": 15, "nextResetTime": 1776519854629},
                {"type": "TOKENS_LIMIT", "unit": 6, "percentage": 32, "nextResetTime": 1776852987997},
                {"type": "TIME_LIMIT",  "unit": 5, "usage": 1000, "currentValue": 5,
                 "remaining": 995, "percentage": 1, "nextResetTime": 1778235387998,
                 "usageDetails": [{"modelCode": "search-prime", "usage": 3}]},
            ],
        },
    }
    with patch.object(mod.urllib.request, "urlopen", return_value=_mock_response(payload)):
        mod._cache.clear()
        plan = mod.PROVIDER.fetch({
            "thresholds": {"critical": 80, "exhausted": 100},
            "providers": {"zai": {"enabled": True, "api_key_file": str(key_file)}},
        })

    assert plan.provider_id == "zai"
    assert plan.short_pct == 15
    assert plan.weekly_pct == 32
    assert plan.plan_tier == "pro"
    assert plan.resets_short_ms == 1776519854629
    assert plan.status_class == "fresh"
    assert plan.details["mcp"]["usage"] == 1000


def test_fetch_returns_stale_when_key_missing():
    mod = _reload_zai()
    mod._cache.clear()
    plan = mod.PROVIDER.fetch({
        "thresholds": {"critical": 80, "exhausted": 100},
        "providers": {"zai": {"enabled": True, "api_key_file": "/nonexistent/key"}},
    })
    assert plan.status_class == "stale"
    assert "no api key" in plan.error.lower()


def test_fetch_returns_stale_on_network_error(tmp_path):
    mod = _reload_zai()
    key_file = tmp_path / "zai-key"
    key_file.write_text("KEY")
    mod._cache.clear()
    with patch.object(mod.urllib.request, "urlopen", side_effect=mod.urllib.error.URLError("offline")):
        plan = mod.PROVIDER.fetch({
            "thresholds": {"critical": 80, "exhausted": 100},
            "providers": {"zai": {"enabled": True, "api_key_file": str(key_file)}},
        })
    assert plan.status_class == "stale"
    assert "network" in plan.error.lower()


def test_fetch_returns_stale_on_non_200_api(tmp_path):
    mod = _reload_zai()
    key_file = tmp_path / "zai-key"
    key_file.write_text("KEY")
    mod._cache.clear()
    with patch.object(mod.urllib.request, "urlopen",
                      return_value=_mock_response({"code": 401, "success": False, "msg": "unauthorized"})):
        plan = mod.PROVIDER.fetch({
            "thresholds": {"critical": 80, "exhausted": 100},
            "providers": {"zai": {"enabled": True, "api_key_file": str(key_file)}},
        })
    assert plan.status_class == "stale"
    assert "unauthorized" in plan.error.lower()


def test_fetch_classifies_critical(tmp_path):
    mod = _reload_zai()
    key_file = tmp_path / "zai-key"
    key_file.write_text("KEY")
    payload = {
        "code": 200, "success": True, "msg": "ok",
        "data": {
            "level": "pro",
            "limits": [
                {"type": "TOKENS_LIMIT", "unit": 3, "percentage": 85, "nextResetTime": 1},
                {"type": "TOKENS_LIMIT", "unit": 6, "percentage": 20, "nextResetTime": 2},
            ],
        },
    }
    mod._cache.clear()
    with patch.object(mod.urllib.request, "urlopen", return_value=_mock_response(payload)):
        plan = mod.PROVIDER.fetch({
            "thresholds": {"critical": 80, "exhausted": 100},
            "providers": {"zai": {"enabled": True, "api_key_file": str(key_file)}},
        })
    assert plan.status_class == "critical"


def test_http_response_is_cached(tmp_path):
    mod = _reload_zai()
    key_file = tmp_path / "zai-key"
    key_file.write_text("KEY")
    payload = {
        "code": 200, "success": True, "msg": "ok",
        "data": {"level": "pro", "limits": []},
    }
    mod._cache.clear()
    cfg = {
        "thresholds": {"critical": 80, "exhausted": 100},
        "providers": {"zai": {"enabled": True, "api_key_file": str(key_file)}},
    }
    with patch.object(mod.urllib.request, "urlopen", return_value=_mock_response(payload)) as mock_urlopen:
        # First call → HTTP
        mod.PROVIDER.fetch(cfg)
        # Second call within TTL → cached, no second HTTP call
        mod.PROVIDER.fetch(cfg)
    assert mock_urlopen.call_count == 1
