"""Shared pytest fixtures.

All state/config paths derive from XDG_*_HOME. Pointing those at temp
directories gives each test a clean filesystem without monkey-patching the
library code.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB = REPO_ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    """Point XDG_CONFIG_HOME + XDG_CACHE_HOME at a temp dir and reload the
    modules that cache those paths at import time."""
    cfg = tmp_path / "config"
    cache = tmp_path / "cache"
    (cfg / "coding-plans").mkdir(parents=True)
    (cache / "coding-plans").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))

    # Reload modules that snapshotted paths at import.
    for name in ("coding_plans.paths", "coding_plans.state", "coding_plans.config"):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    return {"config": cfg / "coding-plans", "cache": cache / "coding-plans"}


@pytest.fixture
def seeded_claude(xdg):
    """Return a helper that seeds Claude state via record_turn()."""
    # Reload claude module so it picks up the reloaded state module.
    import coding_plans.providers.claude as mod

    importlib.reload(mod)

    def _seed(**overrides):
        payload = {
            "session_id": "s-test",
            "model": {"id": "claude-opus-4", "display_name": "Opus 4"},
            "workspace": {"current_dir": "/tmp"},
            "cost": {"total_cost_usd": 1.23, "total_lines_added": 10, "total_lines_removed": 3},
            "context_window": {
                "total_input_tokens": 5000,
                "total_output_tokens": 400,
                "used_percentage": 22,
            },
            "rate_limits": {
                "five_hour": {"used_percentage": 4, "resets_at": 1776519000},
                "seven_day": {"used_percentage": 12, "resets_at": 1776852000},
            },
        }
        payload.update(overrides)
        mod.record_turn(json.dumps(payload))

    return _seed


@pytest.fixture
def write_config(xdg):
    """Write a config.toml into the test's XDG config dir."""
    def _write(body: str) -> Path:
        path = xdg["config"] / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        import coding_plans.config
        importlib.reload(coding_plans.config)
        return path

    return _write
