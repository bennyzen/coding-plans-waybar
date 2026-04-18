"""Provider registry + dynamic loader.

A provider is a Python module in this package named after its provider id
(`claude.py`, `zai.py`, …). Each such module exposes a ``PROVIDER`` module-level
object that satisfies the ``coding_plans.providers.base.Provider`` protocol.

Adding a new provider means:

1. Drop a file ``<id>.py`` here that defines ``PROVIDER``.
2. Add a ``[providers.<id>]`` section to ``~/.config/coding-plans/config.toml``
   with ``enabled = true``.

No registry edits.
"""

from __future__ import annotations

import importlib
from typing import Any

from .base import Provider


def load_enabled(config: dict[str, Any]) -> list[Provider]:
    """Iterate ``[providers.<id>]`` sections of the parsed config, import each
    provider module, and return the enabled ones in config order."""
    enabled: list[Provider] = []
    for pid, pcfg in (config.get("providers") or {}).items():
        if not isinstance(pcfg, dict) or not pcfg.get("enabled", False):
            continue
        try:
            module = importlib.import_module(f"coding_plans.providers.{pid}")
        except ImportError:
            continue
        provider = getattr(module, "PROVIDER", None)
        if provider is None:
            continue
        enabled.append(provider)
    return enabled
