"""statusline orchestration: stdin → record_turn → chain.

``record_turn`` itself is covered by ``test_claude_provider.py``; this
module exercises the ``statusline.py`` glue — the ``main()`` flow and
``run_chained()`` — including the resilience requirements (never crash
Claude Code's statusline over our own bug).
"""

from __future__ import annotations

import importlib
import io
import json
import sys
from unittest.mock import patch


def _reload_statusline():
    """Reload the import chain so statusline picks up the test's XDG paths.

    Order matters: reload claude (for record_turn + STATE_PATH) first,
    then statusline (which imports record_turn + load_config at module
    level).
    """
    import coding_plans.providers.claude as claude_mod

    importlib.reload(claude_mod)
    import coding_plans.statusline as mod

    importlib.reload(mod)
    return mod


def _claude_payload(**overrides):
    payload = {
        "session_id": "s-test",
        "model": {"id": "claude-opus-4", "display_name": "Opus 4"},
        "cost": {
            "total_cost_usd": 1.0,
            "total_lines_added": 5,
            "total_lines_removed": 2,
        },
        "context_window": {
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "used_percentage": 10,
        },
        "rate_limits": {
            "five_hour": {"used_percentage": 4, "resets_at": 1776519000},
            "seven_day": {"used_percentage": 12, "resets_at": 1776852000},
        },
    }
    payload.update(overrides)
    return json.dumps(payload)


# ─── main() orchestration ──────────────────────────────────────────────────


def test_main_writes_state_and_chains(xdg, write_config, monkeypatch):
    """main() should record the Claude turn AND forward the chained
    command's stdout so the user sees their original statusline text."""
    write_config(
        "[providers.claude]\n"
        "enabled = true\n"
        'chained_command = "echo CHAINED-OUTPUT"\n'
    )
    mod = _reload_statusline()

    monkeypatch.setattr(sys, "stdin", io.StringIO(_claude_payload()))
    out = io.StringIO()
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    assert mod.main() == 0

    # State was written.
    state_file = xdg["cache"] / "state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["providers"]["claude"]["session"]["model_name"] == "Opus 4"

    # Chained command ran and its stdout was forwarded.
    assert "CHAINED-OUTPUT" in out.getvalue()


def test_main_silent_on_malformed_stdin(xdg, monkeypatch):
    """Malformed stdin must not crash — the statusline is a hot path."""
    mod = _reload_statusline()
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    err = io.StringIO()
    monkeypatch.setattr(sys, "stderr", err)

    assert mod.main() == 0
    assert not (xdg["cache"] / "state.json").exists()


def test_main_silent_on_empty_stdin(xdg, monkeypatch):
    mod = _reload_statusline()
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert mod.main() == 0
    assert not (xdg["cache"] / "state.json").exists()


# ─── run_chained() ──────────────────────────────────────────────────────────


def test_run_chained_noop_without_command(xdg):
    """No chained_command in cfg → returns silently, writes nothing."""
    mod = _reload_statusline()
    out = io.StringIO()
    with patch.object(sys, "stdout", out):
        mod.run_chained("raw", {"providers": {"claude": {}}})
    assert out.getvalue() == ""


def test_run_chained_forwards_stdout_and_stderr(xdg, monkeypatch):
    mod = _reload_statusline()
    cfg = {
        "providers": {
            "claude": {"chained_command": "printf OUT; printf ERR >&2"}
        }
    }
    out = io.StringIO()
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    mod.run_chained("raw", cfg)

    assert "OUT" in out.getvalue()
    assert "ERR" in err.getvalue()


def test_run_chained_survives_timeout(xdg):
    """A slow chained command must not hang the statusline."""
    mod = _reload_statusline()
    cfg = {"providers": {"claude": {"chained_command": "slow-cmd"}}}
    with patch.object(
        mod.subprocess,
        "run",
        side_effect=mod.subprocess.TimeoutExpired(cmd="slow-cmd", timeout=3),
    ):
        mod.run_chained("raw", cfg)  # must not raise


def test_run_chained_survives_missing_shell(xdg):
    mod = _reload_statusline()
    cfg = {"providers": {"claude": {"chained_command": "anything"}}}
    with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError):
        mod.run_chained("raw", cfg)  # must not raise


def test_run_chained_passes_stdin_to_chained_command(xdg, monkeypatch):
    """The raw statusline JSON must be replayed to the chained command's
    stdin so it can do its own parsing."""
    mod = _reload_statusline()
    cfg = {"providers": {"claude": {"chained_command": "cat"}}}
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)

    mod.run_chained("REPLAY-ME", cfg)

    assert "REPLAY-ME" in out.getvalue()
