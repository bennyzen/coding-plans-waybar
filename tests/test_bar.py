"""End-to-end bar rendering: Claude-only, Z.AI-only, both, errors."""

from __future__ import annotations

import importlib
import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch


def _run_bar():
    import coding_plans.bar as mod
    importlib.reload(mod)
    out = io.StringIO()
    with redirect_stdout(out):
        mod.main()
    return json.loads(out.getvalue())


def test_claude_only(xdg, seeded_claude, write_config):
    seeded_claude()
    write_config("[providers.claude]\nenabled = true\n")
    payload = _run_bar()
    assert payload["class"] == "fresh"
    # Single segment: no join separator doubling.
    assert "·" in payload["text"]
    assert "CLAUDE" in payload["tooltip"]


def test_no_providers_renders_setup_prompt(xdg, write_config):
    write_config("# empty\n")
    payload = _run_bar()
    assert payload["class"] == "empty"
    assert "NO PROVIDERS ENABLED" in payload["tooltip"]


def _mock_zai_response(payload: dict):
    class _Resp:
        def read(self):
            return json.dumps(payload).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    return _Resp()


def test_both_providers(xdg, seeded_claude, write_config, tmp_path):
    seeded_claude()
    zai_key = xdg["config"] / "zai-key"
    zai_key.write_text("FAKE-KEY")
    write_config(f"""
[providers.claude]
enabled = true
[providers.zai]
enabled = true
api_key_file = "{zai_key}"
""")

    zai_payload = {
        "code": 200, "success": True, "msg": "ok",
        "data": {
            "level": "pro",
            "limits": [
                {"type": "TOKENS_LIMIT", "unit": 3, "percentage": 15, "nextResetTime": 1},
                {"type": "TOKENS_LIMIT", "unit": 6, "percentage": 32, "nextResetTime": 2},
            ],
        },
    }
    import coding_plans.providers.zai as zai_mod
    importlib.reload(zai_mod)
    zai_mod._cache.clear()
    with patch.object(zai_mod.urllib.request, "urlopen",
                      return_value=_mock_zai_response(zai_payload)):
        payload = _run_bar()

    # Both Claude and Z.AI segments appear in bar text, separated by the
    # configured join string.
    assert "4%·12%" in payload["text"]
    assert "15%·32%" in payload["text"]
    assert payload["class"] == "fresh"
    assert "CLAUDE" in payload["tooltip"]
    assert "Z.AI" in payload["tooltip"]


def test_zai_api_down_keeps_widget_alive(xdg, seeded_claude, write_config):
    """Z.AI failing must NOT break the overall widget — Claude section
    renders, Z.AI shows stale-with-error."""
    seeded_claude()
    zai_key = xdg["config"] / "zai-key"
    zai_key.write_text("FAKE-KEY")
    write_config(f"""
[providers.claude]
enabled = true
[providers.zai]
enabled = true
api_key_file = "{zai_key}"
""")
    import coding_plans.providers.zai as zai_mod
    importlib.reload(zai_mod)
    zai_mod._cache.clear()
    with patch.object(zai_mod.urllib.request, "urlopen",
                      side_effect=zai_mod.urllib.error.URLError("connection refused")):
        payload = _run_bar()
    # Class goes to "stale" (because Z.AI is stale), but Claude data still appears.
    assert payload["class"] == "stale"
    assert "4%·12%" in payload["text"]
    assert "ERROR:" in payload["tooltip"]


def test_worst_class_wins(xdg, seeded_claude, write_config):
    """With Claude exhausted and Z.AI fresh, aggregate class = exhausted."""
    seeded_claude(rate_limits={
        "five_hour": {"used_percentage": 101, "resets_at": 1776519000},
        "seven_day": {"used_percentage": 50, "resets_at": 1776852000},
    })
    write_config("[providers.claude]\nenabled = true\n")
    payload = _run_bar()
    assert payload["class"] == "exhausted"
