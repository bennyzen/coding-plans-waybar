#!/usr/bin/env bash
# coding-plans-waybar installer.
#
# Run directly:   ./install.sh
# Via curl pipe:  curl -fsSL .../install.sh | bash
#
# Fresh-install only. If you're coming from upstream `claude-usage-waybar`
# run its `uninstall.sh` first — we deliberately don't automate that
# migration (see PLAN.md decision #4).
#
# Idempotent: safe to re-run. Edits to external config files are guarded
# by BEGIN/END marker comments so uninstall.sh can remove them cleanly.

set -euo pipefail

# ───────── colors ────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  C_BLUE=$'\033[34m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'; C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
else
  C_BLUE=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_DIM=""; C_RESET=""
fi
step()  { printf '%s→%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok()    { printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn()  { printf '%s!%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
fail()  { printf '%s✗%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: install.sh [--dry-run]

Installs coding-plans-waybar into:
  ~/.local/bin/                       coding-plans-{bar,popup,statusline,today}
  ~/.local/share/coding-plans-waybar/ Python package + share assets
  ~/.config/coding-plans/config.toml  default config
  ~/.claude/settings.json             statusLine.command (chained if present)
  ~/.config/waybar/config.jsonc       custom/coding-plans module
  ~/.config/waybar/style.css          theming snippet
  ~/.config/systemd/user/             ccusage backfill timer (optional)

Re-run safely; all edits are guarded by BEGIN/END markers.
EOF
      exit 0
      ;;
  esac
done

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '%s[dry-run]%s %s\n' "$C_DIM" "$C_RESET" "$*"
  else
    eval "$@"
  fi
}

# ───────── locate source ─────────────────────────────────────────────────
SRC="$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -d "$SRC/bin" || ! -d "$SRC/lib/coding_plans" ]]; then
  fail "can't find bin/ + lib/coding_plans/ relative to $SRC — run from repo root"
fi

BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
SHARE_DIR="${SHARE_DIR:-$HOME/.local/share/coding-plans-waybar}"
LIB_DIR="$SHARE_DIR/lib"
CFG_DIR="${CFG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/coding-plans}"
CACHE_DIR="${CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/coding-plans}"
WAYBAR_DIR="${WAYBAR_DIR:-$HOME/.config/waybar}"
CLAUDE_SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
SYSTEMD_DIR="${SYSTEMD_DIR:-$HOME/.config/systemd/user}"

# ───────── preflight ─────────────────────────────────────────────────────
step "preflight"

command -v python3 >/dev/null || fail "python3 not found (required)"
ok "python3: $(python3 --version)"

command -v jq >/dev/null || fail "jq not found — install with 'sudo pacman -S jq'"
ok "jq: $(jq --version)"

if ! command -v waybar >/dev/null; then
  warn "waybar not found in PATH — scripts will install, but won't render until waybar is present"
else
  ok "waybar: $(waybar --version 2>&1 | head -1)"
fi

# GTK bindings are typically distro-packaged (python-gobject on Arch) rather
# than in a user-managed Python (mise/pyenv/uv). Probe every python3 on PATH
# plus common absolute locations; pick the first that imports Gtk 4 + Adw.
# That Python becomes the popup's shebang.
POPUP_PYTHON=""
probe_python() {
  local candidate="$1"
  [[ -x "$candidate" ]] || return 1
  "$candidate" -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1'); from gi.repository import Gtk, Adw" >/dev/null 2>&1
}
for cand in /usr/bin/python3 /usr/local/bin/python3 "$(command -v python3 || true)"; do
  if probe_python "$cand"; then
    POPUP_PYTHON="$cand"
    break
  fi
done
if [[ -n "$POPUP_PYTHON" ]]; then
  ok "GTK4 + libadwaita Python bindings: $POPUP_PYTHON"
else
  warn "no python3 with GTK4 + libadwaita bindings — the pop-up won't launch"
  warn "  Arch: sudo pacman -S python-gobject gtk4 libadwaita"
fi

if ! python3 -c "import tomllib" 2>/dev/null && ! python3 -c "import tomli" 2>/dev/null; then
  warn "neither tomllib (py ≥ 3.11) nor tomli is available — config.toml parsing will fall back to defaults silently"
fi

nerd_hit="$(fc-list 2>/dev/null | grep -i nerd | head -1 || true)"
if [[ -z "$nerd_hit" ]]; then
  warn "no Nerd Font detected — provider icons will render as tofu boxes"
else
  ok "Nerd Font detected"
fi

if command -v ccusage >/dev/null \
   || command -v bunx >/dev/null \
   || command -v pnpm >/dev/null \
   || command -v npx  >/dev/null; then
  ok "ccusage runner available (today's Claude tokens + cost will backfill)"
else
  warn "ccusage not installable via ccusage/bunx/pnpm/npx — Claude 'Today' row will stay empty"
fi

# Probe for libgtk4-layer-shell. If present, bake its path into waybar's
# on-click so the popup loads it before libwayland (anchors under the bar).
LAYER_SHELL_LIB=""
for cand in /usr/lib/libgtk4-layer-shell.so.0 \
            /usr/lib64/libgtk4-layer-shell.so.0 \
            /usr/local/lib/libgtk4-layer-shell.so.0; do
  if [[ -f "$cand" ]]; then
    LAYER_SHELL_LIB="$cand"
    break
  fi
done
if [[ -n "$LAYER_SHELL_LIB" ]]; then
  ok "gtk4-layer-shell found: $LAYER_SHELL_LIB (popup anchors under bar)"
else
  warn "gtk4-layer-shell not found — popup will open as a centred window"
fi

if [[ ! -f "$CLAUDE_SETTINGS" ]]; then
  warn "$CLAUDE_SETTINGS not found — will create it"
fi

# ───────── copy bins ─────────────────────────────────────────────────────
step "copy bins → $BIN_DIR"
run "mkdir -p '$BIN_DIR'"
for f in coding-plans-bar coding-plans-popup coding-plans-statusline coding-plans-today; do
  run "install -m 0755 '$SRC/bin/$f' '$BIN_DIR/$f'"
done

# Rewrite the popup shebang to point at a Python that can import GTK/Adw.
# The default #!/usr/bin/env python3 picks up whatever is first on PATH
# (mise, pyenv, venv), which usually lacks python-gobject.
if [[ -n "$POPUP_PYTHON" && -f "$BIN_DIR/coding-plans-popup" ]]; then
  run "sed -i '1c #!$POPUP_PYTHON' '$BIN_DIR/coding-plans-popup'"
  ok "popup shebang → $POPUP_PYTHON"
fi
ok "bins in place"

# ───────── copy lib + share assets ───────────────────────────────────────
step "copy Python package → $LIB_DIR/coding_plans/"
run "mkdir -p '$LIB_DIR'"
# Clean any stale package before copy so removed files don't linger.
run "rm -rf '$LIB_DIR/coding_plans'"
run "cp -R '$SRC/lib/coding_plans' '$LIB_DIR/'"
# Strip pycache that may have snuck in during dev.
run "find '$LIB_DIR/coding_plans' -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true"
ok "package in place"

step "copy share assets → $SHARE_DIR"
run "mkdir -p '$SHARE_DIR/waybar' '$SHARE_DIR/systemd' '$SHARE_DIR/config'"
run "install -m 0644 '$SRC/share/waybar/module.jsonc' '$SHARE_DIR/waybar/module.jsonc'"
run "install -m 0644 '$SRC/share/waybar/style.css'   '$SHARE_DIR/waybar/style.css'"
run "install -m 0644 '$SRC/share/systemd/coding-plans-today.service' '$SHARE_DIR/systemd/coding-plans-today.service'"
run "install -m 0644 '$SRC/share/systemd/coding-plans-today.timer'   '$SHARE_DIR/systemd/coding-plans-today.timer'"
run "install -m 0644 '$SRC/share/config/config.toml.example' '$SHARE_DIR/config/config.toml.example'"
run "install -m 0755 '$SRC/share/_patch_waybar.py' '$SHARE_DIR/_patch_waybar.py'"
run "install -m 0755 '$SRC/share/_patch_style.py'  '$SHARE_DIR/_patch_style.py'"
run "install -m 0755 '$SRC/share/_patch_toml.py'   '$SHARE_DIR/_patch_toml.py'"
# Per-provider brand SVGs live inside the Python package at
# lib/coding_plans/providers/icons/ — they ride along with the cp -R of
# the lib tree a few lines above. Nothing extra to do here.

# Substitute LAYER_SHELL_PRELOAD placeholder in the generated waybar module.
# If the library wasn't found, the env prefix collapses to an empty string
# and the popup falls back to a centred window.
if [[ -n "$LAYER_SHELL_LIB" ]]; then
  preload_env="LD_PRELOAD=$LAYER_SHELL_LIB _CODING_PLANS_POPUP_PRELOADED=1"
else
  preload_env=""
fi
run "sed -i 's|{{LAYER_SHELL_PRELOAD}}|$preload_env|' '$SHARE_DIR/waybar/module.jsonc'"
ok "assets in place"

# ───────── seed config ───────────────────────────────────────────────────
step "seed config → $CFG_DIR/config.toml"
run "mkdir -p '$CFG_DIR'"
if [[ ! -f "$CFG_DIR/config.toml" ]]; then
  run "install -m 0644 '$SRC/share/config/config.toml.example' '$CFG_DIR/config.toml'"
  ok "new config.toml written (edit to taste)"
else
  ok "existing config.toml left untouched"
fi

# If the user has a Z.AI key from upstream `claude-usage-waybar`, carry it
# over — opt-in migration, only when the file literally already exists.
legacy_zai_key="${XDG_CONFIG_HOME:-$HOME/.config}/claude-usage/zai-key"
if [[ -f "$legacy_zai_key" && ! -f "$CFG_DIR/zai-key" ]]; then
  run "install -m 0600 '$legacy_zai_key' '$CFG_DIR/zai-key'"
  ok "copied Z.AI key from $legacy_zai_key → $CFG_DIR/zai-key"
fi

run "mkdir -p '$CACHE_DIR'"

# ───────── register Claude statusLine ────────────────────────────────────
step "register statusLine in $CLAUDE_SETTINGS"
if [[ -f "$CLAUDE_SETTINGS" ]]; then
  existing="$(jq -r '.statusLine.command // ""' "$CLAUDE_SETTINGS" 2>/dev/null || echo "")"
else
  existing=""
fi

# If there's a pre-existing statusLine that isn't ours, stash it in config
# so our statusline can chain to it (user sees their original text too).
if [[ -n "$existing" && "$existing" != *"coding-plans-statusline"* && "$existing" != *"claude-usage-statusline"* ]]; then
  warn "existing statusLine will be chained: $existing"
  EXISTING_STATUSLINE="$existing" CFG_DIR_EXPORT="$CFG_DIR" run "python3 '$SRC/share/_patch_toml.py' set-chained"
  ok "chained_command recorded in config.toml under [providers.claude]"
fi

new_cmd="$BIN_DIR/coding-plans-statusline"
if [[ -f "$CLAUDE_SETTINGS" ]]; then
  run "jq --arg cmd '$new_cmd' '
    .statusLine = { type: \"command\", command: \$cmd }
  ' '$CLAUDE_SETTINGS' > '$CLAUDE_SETTINGS.tmp' && mv '$CLAUDE_SETTINGS.tmp' '$CLAUDE_SETTINGS'"
else
  run "mkdir -p '$(dirname "$CLAUDE_SETTINGS")'"
  run "jq -n --arg cmd '$new_cmd' '{ statusLine: { type: \"command\", command: \$cmd } }' > '$CLAUDE_SETTINGS'"
fi
ok "statusLine.command → $new_cmd"

# ───────── patch waybar config ───────────────────────────────────────────
# Waybar's default config lives at ~/.config/waybar/config.jsonc, but Omarchy
# and many ML4W-style setups use a bare ~/.config/waybar/config (no ext) or
# a per-theme file under themes/<name>/config. Honour $WAYBAR_CONFIG if set,
# otherwise probe in order.
WAYBAR_CFG="${WAYBAR_CONFIG:-}"
if [[ -z "$WAYBAR_CFG" ]]; then
  for cand in "$WAYBAR_DIR/config.jsonc" "$WAYBAR_DIR/config.json" "$WAYBAR_DIR/config"; do
    if [[ -f "$cand" ]]; then
      WAYBAR_CFG="$cand"
      break
    fi
  done
fi

step "patch waybar config"
if [[ -z "$WAYBAR_CFG" || ! -f "$WAYBAR_CFG" ]]; then
  warn "no waybar config found under $WAYBAR_DIR (tried config.jsonc, config.json, config). Add this block manually to any config that waybar loads:"
  printf '%s\n' "$C_DIM"
  # Print from the source tree so --dry-run works even before assets copy.
  cat "$SRC/share/waybar/module.jsonc"
  printf '%s\n' "$C_RESET"
else
  run "cp '$WAYBAR_CFG' '$WAYBAR_CFG.bak.coding-plans'"
  run "python3 '$SHARE_DIR/_patch_waybar.py' install '$WAYBAR_CFG' '$SHARE_DIR/waybar/module.jsonc'"
  ok "custom/coding-plans added to $WAYBAR_CFG (backup at $WAYBAR_CFG.bak.coding-plans)"
fi

step "patch $WAYBAR_DIR/style.css"
if [[ -f "$WAYBAR_DIR/style.css" ]]; then
  run "cp '$WAYBAR_DIR/style.css' '$WAYBAR_DIR/style.css.bak.coding-plans'"
  run "python3 '$SHARE_DIR/_patch_style.py' install '$WAYBAR_DIR/style.css' '$SHARE_DIR/waybar/style.css'"
  ok "styling appended (backup at style.css.bak.coding-plans)"
else
  warn "no style.css to patch — theming skipped"
fi

# ───────── systemd user timer (optional) ─────────────────────────────────
if command -v systemctl >/dev/null; then
  step "install systemd user timer (optional)"
  run "mkdir -p '$SYSTEMD_DIR'"
  run "install -m 0644 '$SRC/share/systemd/coding-plans-today.service' '$SYSTEMD_DIR/coding-plans-today.service'"
  run "install -m 0644 '$SRC/share/systemd/coding-plans-today.timer'   '$SYSTEMD_DIR/coding-plans-today.timer'"
  run "systemctl --user daemon-reload || true"
  run "systemctl --user enable --now coding-plans-today.timer || true"
  # Trigger one immediate backfill so Today isn't 0/0 until the first tick.
  run "systemctl --user start coding-plans-today.service || true"
  ok "timer enabled + first backfill triggered"
  ok "  (disable later with: systemctl --user disable --now coding-plans-today.timer)"
else
  warn "systemctl not available — skipping timer install"
fi

# ───────── reload waybar ─────────────────────────────────────────────────
if pgrep -x waybar >/dev/null; then
  step "reload waybar"
  run "pkill -SIGUSR2 waybar || waybar -r 2>/dev/null || true"
  ok "sent reload signal"
else
  warn "waybar not running — start it to see the new module"
fi

echo
ok "installation complete"
echo "  • edit        $CFG_DIR/config.toml"
echo "  • Z.AI key    chmod 600 $CFG_DIR/zai-key  (paste the raw key, no 'Bearer ' prefix)"
echo "  • click bar   to open the pop-up"
echo "  • uninstall   $SRC/uninstall.sh"
