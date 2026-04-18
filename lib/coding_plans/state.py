"""Shared state file for all providers.

One file lives at ``~/.cache/coding-plans/state.json`` with shape::

    { "schema": 2, "providers": { "<id>": { ... } } }

Each provider owns its own slice under ``providers.<id>``. Writes are atomic
(temp file + rename) so a half-written state never corrupts the renderer.

Stateless providers (e.g. Z.AI, which polls live) don't need to touch this
file at all — the missing slice just means ``provider_state()`` returns an
empty dict.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .paths import CACHE_DIR, STATE_PATH

SCHEMA_VERSION = 2

EMPTY_STATE: dict[str, Any] = {"schema": SCHEMA_VERSION, "providers": {}}


def load_state(path: Path | None = None) -> dict[str, Any]:
    target = path or STATE_PATH
    if not target.exists():
        return {"schema": SCHEMA_VERSION, "providers": {}}
    try:
        with target.open("r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"schema": SCHEMA_VERSION, "providers": {}}
    state.setdefault("schema", SCHEMA_VERSION)
    state.setdefault("providers", {})
    return state


def write_state(state: dict[str, Any], path: Path | None = None) -> None:
    target = path or STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(f".tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, separators=(",", ":"))
    os.replace(tmp, target)


def provider_state(state: dict[str, Any], provider_id: str) -> dict[str, Any]:
    """Return the ``providers.<id>`` slice, or an empty dict if absent."""
    return (state.get("providers") or {}).get(provider_id) or {}


def set_provider_state(state: dict[str, Any], provider_id: str, slice_: dict[str, Any]) -> None:
    state.setdefault("providers", {})[provider_id] = slice_


__all__ = [
    "CACHE_DIR",
    "EMPTY_STATE",
    "SCHEMA_VERSION",
    "STATE_PATH",
    "load_state",
    "provider_state",
    "set_provider_state",
    "write_state",
]
