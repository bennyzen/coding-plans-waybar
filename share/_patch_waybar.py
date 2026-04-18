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

import re
import sys
from pathlib import Path

BEGIN = "// >>> coding-plans-waybar >>>"
END = "// <<< coding-plans-waybar <<<"
MODULE_NAME = '"custom/coding-plans"'


def strip_block(text: str) -> str:
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.DOTALL)
    return pattern.sub("", text)


def already_in_modules_right(text: str) -> bool:
    match = re.search(r'"modules-right"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if not match:
        return False
    return MODULE_NAME in match.group(1)


def add_to_modules_right(text: str) -> str:
    def injector(match: re.Match[str]) -> str:
        contents = match.group(1)
        if MODULE_NAME in contents:
            return match.group(0)
        # Place ours right after "custom/claude" if that exists, else at front.
        after = '"custom/claude"'
        if after in contents:
            return match.group(0).replace(after, f'{after},\n    {MODULE_NAME}', 1)
        # Insert as the first entry.
        return match.group(0).replace("[", f"[\n    {MODULE_NAME},", 1)

    return re.sub(r'"modules-right"\s*:\s*\[(.*?)\]', injector, text, count=1, flags=re.DOTALL)


def remove_from_modules_right(text: str) -> str:
    def stripper(match: re.Match[str]) -> str:
        contents = match.group(1)
        new = re.sub(r',?\s*' + re.escape(MODULE_NAME), "", contents)
        new = re.sub(r'\[\s*,', "[", new)
        return f'"modules-right": [{new}]'

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
    module_body = module_path.read_text(encoding="utf-8")
    text = insert_module_block(text, module_body)
    text = add_to_modules_right(text)
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
