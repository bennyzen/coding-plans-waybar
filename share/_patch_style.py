#!/usr/bin/env python3
"""Append (or rewrite) the coding-plans-waybar block in ~/.config/waybar/style.css.

Guarded by marker comments; running install twice replaces the block.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BEGIN = "/* >>> coding-plans-waybar >>> */"
END = "/* <<< coding-plans-waybar <<< */"


def strip_block(text: str) -> str:
    return re.sub(
        re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?",
        "",
        text,
        flags=re.DOTALL,
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: _patch_style.py install <style.css> <snippet.css> | uninstall <style.css>", file=sys.stderr)
        return 2
    cmd = argv[1]
    path = Path(argv[2])
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    text = strip_block(text)
    if cmd == "install":
        snippet = Path(argv[3]).read_text(encoding="utf-8")
        text = text.rstrip() + "\n\n" + BEGIN + "\n" + snippet.strip() + "\n" + END + "\n"
    elif cmd != "uninstall":
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
