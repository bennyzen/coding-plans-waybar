"""``bin/coding-plans-today`` — the ccusage backfill script.

This is the one piece of shell in the project. It runs ``ccusage daily
--json``, pipes it through ``jq``, and atomically merges the result into
``~/.cache/coding-plans/state.json`` under ``providers.claude.today``.

These tests stub ``ccusage`` on ``PATH`` with a fake that emits a fixture
payload, then assert the script produced the expected state. Covers the
happy path, pre-existing-state preservation, and the empty-output
early-exit.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "bin" / "coding-plans-today"

_CCUSAGE_FIXTURE = json.dumps(
    {
        "daily": [
            {
                "date": "20260711",
                "inputTokens": 1000,
                "outputTokens": 500,
                "cacheCreationTokens": 200,
                "cacheReadTokens": 100,
                "totalTokens": 1800,
                "totalCost": 0.05,
                "modelsUsed": ["claude-opus-4", "claude-sonnet-4"],
            }
        ]
    }
)


def _make_fake_ccusage(
    bindir: Path, fixture: str = _CCUSAGE_FIXTURE
) -> str:
    """Plant a fake ``ccusage`` on PATH that prints ``fixture``."""
    bindir.mkdir(parents=True, exist_ok=True)
    exe = bindir / "ccusage"
    exe.write_text(f"#!/bin/bash\necho '{fixture}'\n")
    exe.chmod(0o755)
    return str(bindir)


def _run_script(cache_dir: Path, path_prefix: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "XDG_CACHE_HOME": str(cache_dir),
        "PATH": f"{path_prefix}:{os.environ['PATH']}",
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )


# ─── Happy path ─────────────────────────────────────────────────────────────


def test_merges_ccusage_into_fresh_state(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    binpath = _make_fake_ccusage(tmp_path / "bin")

    result = _run_script(cache, binpath)
    assert result.returncode == 0, result.stderr

    state_file = cache / "coding-plans" / "state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())

    assert state["schema"] == 2
    claude = state["providers"]["claude"]
    today = claude["today"]
    assert today["tokens"] == 1800
    assert today["cost_usd"] == 0.05
    # jq strips "claude-" prefix and trailing version number:
    # "claude-opus-4" → "opus", "claude-sonnet-4" → "sonnet".
    assert today["models"] == ["opus", "sonnet"]

    # The script seeds the full default slice on a fresh state — sanity
    # check that the five_hour / session skeletons are present too.
    assert "five_hour" in claude
    assert "session" in claude


def test_preserves_existing_state(tmp_path):
    """A today-only backfill must NOT clobber five_hour / session fields
    that the statusline wrote."""
    cache = tmp_path / "cache"
    cache.mkdir()
    state_dir = cache / "coding-plans"
    state_dir.mkdir()
    state_file = state_dir / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "schema": 2,
                "providers": {
                    "claude": {
                        "five_hour": {"pct": 42, "resets_at": 9999},
                        "session": {"id": "sess-1", "model_name": "Opus"},
                    }
                },
            }
        )
    )

    binpath = _make_fake_ccusage(tmp_path / "bin")
    result = _run_script(cache, binpath)
    assert result.returncode == 0, result.stderr

    state = json.loads(state_file.read_text())
    claude = state["providers"]["claude"]

    # Today was written.
    assert claude["today"]["tokens"] == 1800
    # Pre-existing fields survived untouched.
    assert claude["five_hour"]["pct"] == 42
    assert claude["session"]["model_name"] == "Opus"


def test_empty_ccusage_output_exits_clean(tmp_path):
    """When ccusage produces no output (e.g. no usage today), the script
    must exit 0 without writing a state file."""
    cache = tmp_path / "cache"
    cache.mkdir()
    binpath = _make_fake_ccusage(tmp_path / "bin", fixture="")

    result = _run_script(cache, binpath)
    assert result.returncode == 0
    assert not (cache / "coding-plans" / "state.json").exists()


def test_empty_daily_array_writes_zero_totals(tmp_path):
    """An empty ``daily`` array yields a valid (zero) summary, not null —
    the script writes a state file with zeros rather than bailing."""
    cache = tmp_path / "cache"
    cache.mkdir()
    binpath = _make_fake_ccusage(
        tmp_path / "bin", fixture=json.dumps({"daily": []})
    )

    result = _run_script(cache, binpath)
    assert result.returncode == 0

    state_file = cache / "coding-plans" / "state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    today = state["providers"]["claude"]["today"]
    assert today["tokens"] == 0
    assert today["cost_usd"] == 0
    assert today["models"] == []
