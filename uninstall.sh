#!/usr/bin/env bash
# coding-plans-waybar — remove everything this tool installed.
# Leaves backups (*.bak.coding-plans) in place.

set -euo pipefail

if [[ -t 1 ]]; then
  C_BLUE=$'\033[34m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RESET=$'\033[0m'
else
  C_BLUE=""; C_GREEN=""; C_YELLOW=""; C_RESET=""
fi
step()  { printf '%s→%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok()    { printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn()  { printf '%s!%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }

BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
SHARE_DIR="${SHARE_DIR:-$HOME/.local/share/coding-plans-waybar}"
CFG_DIR="${CFG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/coding-plans}"
WAYBAR_DIR="${WAYBAR_DIR:-$HOME/.config/waybar}"
CLAUDE_SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
SYSTEMD_DIR="${SYSTEMD_DIR:-$HOME/.config/systemd/user}"

step "disable systemd timer"
if command -v systemctl >/dev/null; then
  systemctl --user disable --now coding-plans-today.timer 2>/dev/null || true
  rm -f "$SYSTEMD_DIR/coding-plans-today.service" "$SYSTEMD_DIR/coding-plans-today.timer"
  systemctl --user daemon-reload 2>/dev/null || true
  ok "timer removed"
fi

step "remove bins"
for f in coding-plans-bar coding-plans-popup coding-plans-statusline coding-plans-today; do
  rm -f "$BIN_DIR/$f"
done
ok "bins removed"

step "revert ~/.claude/settings.json"
if [[ -f "$CLAUDE_SETTINGS" ]]; then
  current="$(jq -r '.statusLine.command // ""' "$CLAUDE_SETTINGS" 2>/dev/null || echo "")"
  if [[ "$current" == *"coding-plans-statusline"* ]]; then
    # Try to recover the chained command from config.toml before we wipe
    # the share dir / config.
    if [[ -x "$SHARE_DIR/_patch_toml.py" ]]; then
      chained="$(CFG_DIR_EXPORT="$CFG_DIR" python3 "$SHARE_DIR/_patch_toml.py" get-chained 2>/dev/null || echo "")"
    else
      chained="$(CFG_DIR_EXPORT="$CFG_DIR" python3 -c "
import os
from pathlib import Path
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        raise SystemExit(0)
p = Path(os.environ['CFG_DIR_EXPORT']) / 'config.toml'
if p.exists():
    try:
        data = tomllib.loads(p.read_text())
        providers = data.get('providers') or {}
        claude = providers.get('claude') or {}
        print(claude.get('chained_command') or '', end='')
    except Exception:
        pass
" 2>/dev/null || echo "")"
    fi
    if [[ -n "$chained" ]]; then
      jq --arg cmd "$chained" '.statusLine = { type: "command", command: $cmd }' "$CLAUDE_SETTINGS" > "$CLAUDE_SETTINGS.tmp"
      mv "$CLAUDE_SETTINGS.tmp" "$CLAUDE_SETTINGS"
      ok "restored original statusLine → $chained"
    else
      jq 'del(.statusLine)' "$CLAUDE_SETTINGS" > "$CLAUDE_SETTINGS.tmp"
      mv "$CLAUDE_SETTINGS.tmp" "$CLAUDE_SETTINGS"
      ok "statusLine cleared"
    fi
  else
    warn "statusLine not pointing at us — leaving untouched"
  fi
fi

step "revert waybar config"
# Same probing logic as install.sh: honour $WAYBAR_CONFIG, else try common
# filenames in $WAYBAR_DIR.
WAYBAR_CFG="${WAYBAR_CONFIG:-}"
if [[ -z "$WAYBAR_CFG" ]]; then
  for cand in "$WAYBAR_DIR/config.jsonc" "$WAYBAR_DIR/config.json" "$WAYBAR_DIR/config"; do
    if [[ -f "$cand" ]]; then
      WAYBAR_CFG="$cand"
      break
    fi
  done
fi

if [[ -n "$WAYBAR_CFG" && -f "$WAYBAR_CFG" ]]; then
  if [[ -f "$SHARE_DIR/_patch_waybar.py" ]]; then
    python3 "$SHARE_DIR/_patch_waybar.py" uninstall "$WAYBAR_CFG"
  else
    # Fall back to inline python if the share dir is already gone.
    WAYBAR_CFG_ARG="$WAYBAR_CFG" python3 -c "
import os, re
from pathlib import Path
p = Path(os.environ['WAYBAR_CFG_ARG'])
t = p.read_text()
t = re.sub(r'// >>> coding-plans-waybar >>>.*?// <<< coding-plans-waybar <<<\n?', '', t, flags=re.DOTALL)
t = re.sub(r',?\s*\"custom/coding-plans\"', '', t)
p.write_text(t)
"
  fi
  ok "custom/coding-plans removed from $WAYBAR_CFG"
fi

step "revert waybar style.css"
if [[ -f "$WAYBAR_DIR/style.css" ]]; then
  python3 -c "
import re
from pathlib import Path
p = Path('$WAYBAR_DIR/style.css')
t = p.read_text()
t = re.sub(r'/\* >>> coding-plans-waybar >>> \*/.*?/\* <<< coding-plans-waybar <<< \*/\n?', '', t, flags=re.DOTALL)
p.write_text(t)
"
  ok "styling removed"
fi

step "remove share + cache"
rm -rf "$SHARE_DIR"
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/coding-plans"
ok "share + cache removed"

echo
ok "uninstall complete"
echo "  • config at $CFG_DIR was left alone — delete it manually if you like"
echo "  • Z.AI key at $CFG_DIR/zai-key is also preserved"
if pgrep -x waybar >/dev/null; then
  pkill -SIGUSR2 waybar || waybar -r 2>/dev/null || true
fi
