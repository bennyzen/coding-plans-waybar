#!/usr/bin/env python3
"""Safe TOML edits that don't involve shell quoting.

Usage:
    _patch_toml.py set-chained          # reads $EXISTING_STATUSLINE + $CFG_DIR_EXPORT
    _patch_toml.py get-chained          # prints chained_command (or empty) to stdout

Writes/reads ``[providers.claude].chained_command`` in config.toml.
Using a dedicated script avoids quoting disasters when the target value
contains quotes, tildes, or backslashes.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def _cfg_path() -> Path:
    cfg_dir = os.environ.get("CFG_DIR_EXPORT") or (
        (os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config"))
        + "/coding-plans"
    )
    return Path(cfg_dir) / "config.toml"


def set_chained() -> int:
    value = os.environ.get("EXISTING_STATUSLINE", "")
    if not value:
        return 0
    path = _cfg_path()
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")

    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    replacement = f'chained_command = "{escaped}"'

    # Replace the first `chained_command = "..."` under [providers.claude].
    # We match the entire section and substitute within.
    claude_section = re.compile(
        r'(\[providers\.claude\][^\[]*?chained_command\s*=\s*)"[^"]*"',
        re.DOTALL,
    )
    new_text, n = claude_section.subn(lambda m: m.group(1) + f'"{escaped}"', text, count=1)
    if n == 0:
        # Key absent — append under [providers.claude] if present, else at EOF.
        if "[providers.claude]" in new_text:
            def _inject(m: re.Match[str]) -> str:
                return m.group(1).rstrip() + f"\n{replacement}\n" + m.group(2)
            new_text = re.sub(
                r'(\[providers\.claude\][^\[]*?)(\n\[|\Z)',
                _inject,
                new_text,
                count=1,
                flags=re.DOTALL,
            )
        else:
            new_text = new_text.rstrip() + f"\n\n[providers.claude]\nenabled = true\n{replacement}\n"
    path.write_text(new_text, encoding="utf-8")
    return 0


def get_chained() -> int:
    path = _cfg_path()
    if not path.exists():
        return 0
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return 0
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    providers = data.get("providers") or {}
    claude = providers.get("claude") or {}
    value = claude.get("chained_command") or ""
    sys.stdout.write(value)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: _patch_toml.py set-chained | get-chained", file=sys.stderr)
        return 2
    if argv[1] == "set-chained":
        return set_chained()
    if argv[1] == "get-chained":
        return get_chained()
    print(f"unknown command: {argv[1]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
