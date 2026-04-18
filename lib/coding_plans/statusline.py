"""Claude Code statusLine emitter entry point — stub."""

from __future__ import annotations

import sys


def main() -> int:
    # Read stdin so Claude Code doesn't block on a full pipe buffer.
    try:
        sys.stdin.read()
    except Exception:
        pass
    return 0
