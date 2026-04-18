"""Claude Code statusLine emitter.

Registered as ``statusLine.command`` in ``~/.claude/settings.json``. Claude
Code pipes JSON to stdin on every turn. We extract rate_limits + session info,
merge into ``~/.cache/coding-plans/state.json`` under ``providers.claude``,
and (optionally) chain to a pre-existing statusline script so the user's
original statusline text still renders.

Contract (from upstream):
- Read ALL of stdin (buffer it, we may need to replay to the chained command).
- Never crash: even if stdin is empty or malformed, exit 0.
- Emit the chained command's stdout unchanged, or print nothing.
"""

from __future__ import annotations

import subprocess
import sys

from .config import load_config
from .providers.claude import record_turn


def _chained_command(cfg: dict) -> str:
    providers = cfg.get("providers") or {}
    claude_cfg = providers.get("claude") or {}
    return (claude_cfg.get("chained_command") or "").strip()


def run_chained(raw: str, cfg: dict) -> None:
    cmd = _chained_command(cfg)
    if not cmd:
        return
    # /bin/sh -c handles ~ and $VAR expansion — no Python-level expansion needed.
    try:
        result = subprocess.run(
            ["/bin/sh", "-c", cmd],
            input=raw,
            text=True,
            capture_output=True,
            timeout=3,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)


def main() -> int:
    try:
        raw = sys.stdin.read()
    except (KeyboardInterrupt, OSError):
        return 0

    try:
        record_turn(raw)
    except Exception as exc:  # never break the user's statusline
        print(f"coding-plans-statusline: {exc}", file=sys.stderr)

    try:
        cfg = load_config()
        run_chained(raw, cfg)
    except Exception as exc:
        print(f"coding-plans-statusline chain: {exc}", file=sys.stderr)

    return 0
