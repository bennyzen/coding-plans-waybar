#!/usr/bin/env python3
"""Patch ~/.config/waybar/config.jsonc to add/remove the custom/coding-plans
module. JSONC has comments which `jq` would strip, so we do marker-guarded
line edits instead — safer and preserves the user's formatting.

Usage:
    _patch_waybar.py install <config.jsonc> <module.jsonc>
    _patch_waybar.py uninstall <config.jsonc>

Idempotent: running install twice replaces the existing block between
markers; running uninstall on a clean file is a no-op.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

BEGIN = "// >>> coding-plans-waybar >>>"
END = "// <<< coding-plans-waybar <<<"
# Anchor the modules-right insertion after this entry if present. Falls back
# to "custom/claude" (common on claude-usage-waybar holdovers), then
# prepends to the array.
INSERT_AFTER = os.environ.get("CODING_PLANS_INSERT_AFTER", "").strip()
# Matches both the legacy single-module name and every per-provider name.
MODULE_NAME_RE = re.compile(r'"custom/coding-plans(?:-[a-z0-9]+)?"')


def strip_block(text: str) -> str:
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.DOTALL)
    return pattern.sub("", text)


def _module_names_from_block(module_body: str) -> list[str]:
    """Pull every ``"custom/coding-plans-<id>"`` key name from the generated
    block. Order matches the block (which mirrors config.toml order)."""
    return MODULE_NAME_RE.findall(module_body)


def add_to_modules_right(text: str, module_names: list[str]) -> str:
    """Insert each module name into ``"modules-right"`` if not already
    present. Anchor via ``$CODING_PLANS_INSERT_AFTER`` env var, else
    ``"custom/claude"`` holdover, else front-of-array."""

    def injector(match: re.Match[str]) -> str:
        contents = match.group(1)
        to_add = [n for n in module_names if n not in contents]
        if not to_add:
            return match.group(0)
        insertion = ",\n        ".join(to_add)
        for anchor_name in (INSERT_AFTER, "custom/claude"):
            if not anchor_name:
                continue
            anchor = f'"{anchor_name}"'
            if anchor in contents:
                return match.group(0).replace(anchor, f'{anchor},\n        {insertion}', 1)
        return match.group(0).replace("[", f"[\n        {insertion},", 1)

    return re.sub(r'"modules-right"\s*:\s*\[(.*?)\]', injector, text, count=1, flags=re.DOTALL)


def remove_from_modules_right(text: str) -> str:
    """Strip every ``"custom/coding-plans..."`` entry (legacy + per-provider)."""
    def stripper(match: re.Match[str]) -> str:
        contents = MODULE_NAME_RE.sub("", match.group(1))
        # Repeatedly collapse dangling commas until stable — re.sub is
        # non-overlapping so a single pass leaves pairs untouched when
        # providers land on consecutive lines.
        while True:
            collapsed = re.sub(r',\s*,', ",", contents)
            if collapsed == contents:
                break
            contents = collapsed
        # ``contents`` is the inside of [...] — anchor with \A/\Z, not the brackets.
        contents = re.sub(r'\A\s*,', "", contents)  # leading comma
        contents = re.sub(r',\s*\Z', "", contents)  # trailing comma
        return f'"modules-right": [{contents}]'

    return re.sub(r'"modules-right"\s*:\s*\[(.*?)\]', stripper, text, count=1, flags=re.DOTALL)


def insert_module_block(text: str, module_body: str) -> str:
    block = f"{BEGIN}\n{module_body.strip()}\n{END}\n"
    # Find the closing brace of the outermost object — last '}' in the file.
    last_close = text.rfind("}")
    if last_close == -1:
        raise SystemExit("waybar config has no closing brace")
    before = text[:last_close].rstrip()
    after = text[last_close:]
    if not before.endswith(",") and not before.endswith("{"):
        before = before + ","
    return before + "\n  " + block.replace("\n", "\n  ").rstrip() + "\n" + after


def install(config_path: Path, module_path: Path) -> None:
    text = config_path.read_text(encoding="utf-8")
    text = strip_block(text)
    # Also strip any stale modules-right entries before re-adding — lets
    # re-runs reorder providers after the user toggles enabled/disabled.
    text = remove_from_modules_right(text)
    module_body = module_path.read_text(encoding="utf-8")
    text = insert_module_block(text, module_body)
    text = add_to_modules_right(text, _module_names_from_block(module_body))
    config_path.write_text(text, encoding="utf-8")


def uninstall(config_path: Path) -> None:
    text = config_path.read_text(encoding="utf-8")
    text = strip_block(text)
    text = remove_from_modules_right(text)
    config_path.write_text(text, encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "install":
        if len(argv) < 4:
            print("install requires <config.jsonc> <module.jsonc>", file=sys.stderr)
            return 2
        install(Path(argv[2]), Path(argv[3]))
    elif cmd == "uninstall":
        if len(argv) < 3:
            print("uninstall requires <config.jsonc>", file=sys.stderr)
            return 2
        uninstall(Path(argv[2]))
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
