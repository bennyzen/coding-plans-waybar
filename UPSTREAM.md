# Upstream attribution

This project is a soft-fork of [infiniV/claude-usage-waybar](https://github.com/infiniV/claude-usage-waybar) — a Claude-only Waybar widget. The upstream project's Claude Code statusline integration, `ccusage` backfill, Pango tooltip aesthetic, and GTK4/libadwaita popup are preserved here almost verbatim. What's new is the provider layer: a `Provider` protocol so a single Waybar module can render multiple AI coding-plan subscriptions (Claude, Z.AI, …).

## What was taken from upstream

| Upstream file | Where it lives here | Changes |
|---|---|---|
| `bin/claude_usage.py` | `lib/coding_plans/state.py`, `lib/coding_plans/formatters.py`, `lib/coding_plans/palette.py` | Split by concern. State/config helpers, human-readable formatters, and the baked palette + Omarchy theme overlay are unchanged. |
| `bin/claude-usage-bar` | `lib/coding_plans/bar.py` + `lib/coding_plans/providers/claude.py` | Renderer generalised over a `Provider` protocol. Claude-specific fetch logic moved into the provider. |
| `bin/claude-usage-popup` | `lib/coding_plans/popup.py` + `lib/coding_plans/providers/claude.py` | Same widget hierarchy and CSS; per-provider cards are now rendered in a loop. Claude's card matches upstream's 4-row layout. |
| `bin/claude-usage-statusline` | `bin/coding-plans-statusline` | Rename + paths only. Unchanged behaviour: reads Claude Code JSON, updates state, chains to the user's prior statusline. |
| `bin/claude-usage-today` | `bin/coding-plans-today` | Rename + state-file path only. |
| `share/waybar/module.jsonc` | `share/waybar/module.jsonc` | Renamed the Waybar custom name, same `on-click` / `LD_PRELOAD` dance for gtk4-layer-shell. |
| `share/waybar/style.css` | `share/waybar/style.css` | Same thresholds/classes, new selector `#custom-coding-plans`. |
| `share/systemd/claude-usage-today.{service,timer}` | `share/systemd/coding-plans-today.{service,timer}` | Renamed, same ccusage-every-5-min cadence. |
| `share/_patch_{waybar,style,toml}.py` | `share/_patch_{waybar,style,toml}.py` | Marker strings changed to `coding-plans-waybar`. |
| `install.sh` / `uninstall.sh` | `install.sh` / `uninstall.sh` | Rewritten. Upstream's flow (copy, patch `~/.claude/settings.json`, patch Waybar config, enable timer, reload Waybar) is preserved; we dropped the upstream-migration path because our target audience is fresh installs. |

## What's new

- `lib/coding_plans/providers/base.py` — `Provider` protocol + `PlanStatus` dataclass.
- `lib/coding_plans/providers/zai.py` — Z.AI Coding Plan via `/api/monitor/usage/quota/limit`.
- Config shape is namespaced by provider under `[providers.<id>]`. See `share/config/config.toml.example`.
- `PROVIDERS.md` documents how to add a third provider.

## Sync policy

This is a *soft* fork. We do not track upstream's commits line-by-line. When upstream ships a fix that applies to the Claude provider (e.g. a Claude Code schema change), we cherry-pick it into `lib/coding_plans/providers/claude.py` or the shared renderer.

Upstream reference clone (for development): `git clone --depth 1 https://github.com/infiniV/claude-usage-waybar /tmp/upstream-claude-usage-waybar`.
