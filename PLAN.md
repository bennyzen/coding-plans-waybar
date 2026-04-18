# coding-plans-waybar — Implementation Plan

A single Waybar widget that shows usage across multiple AI coding-plan subscriptions (Claude, Z.AI, eventually Moonshot/Qwen/Dashscope). Soft-fork of [infiniV/claude-usage-waybar](https://github.com/infiniV/claude-usage-waybar).

## Current state (2026-04-18)

The user has **two separate waybar modules running right now** that this project replaces:

- `custom/claude-usage` — vanilla upstream `claude-usage-waybar`, already installed at `~/.local/bin/claude-usage-*` and `~/.local/share/claude-usage-waybar/`. Reads Claude Code's statusline stdin + `ccusage daily --json`. State at `~/.cache/claude-usage/state.json`, config at `~/.config/claude-usage/config.toml`.
- `custom/zai-usage` — a one-off bash script `~/.local/bin/zai-usage-bar` wrote during migration. Polls `https://api.z.ai/api/monitor/usage/quota/limit` every 30s with the API key from `~/.config/claude-usage/zai-key` (chmod 600). Output is compact waybar JSON with tooltip.

Both are wired into `~/.config/waybar/themes/bennyzen/config` in `modules-right`, with matching `#custom-*-usage.{fresh,stale,critical,exhausted,empty}` classes appended to `bennyzen/style.css`.

**Goal:** replace both with a single `custom/coding-plans` module.

## Upstream architecture (what we're starting from)

`claude-usage-waybar` ships four Python executables:

| Binary | Purpose |
|---|---|
| `claude-usage-bar` | reads state.json, prints waybar JSON (bar label + rich tooltip) every 15s |
| `claude-usage-popup` | GTK4/libadwaita popover anchored under the bar (on-click) |
| `claude-usage-statusline` | wrapper over the user's existing Claude Code statusLine; receives Claude's JSON stdin, extracts session/context info, updates state.json, and chains the old statusline so it still prints |
| `claude-usage-today` | shells out to `ccusage daily --json`, merges today's token/cost into state.json (run by a user systemd timer) |

State flow: Claude Code pipes JSON to `claude-usage-statusline` on every turn → writes `state.json` → `claude-usage-bar` reads state.json every 15s → waybar renders. Separately, `claude-usage-today.timer` backfills the "today" row from ccusage.

Important: **upstream only works for Claude**. It assumes Anthropic's 5h / weekly window semantics, it reads Claude-Code-specific JSONL, and ccusage is Claude-focused.

## Z.AI data source (the missing half)

Z.AI exposes a ready-made quota endpoint (no JSONL parsing needed):

```
GET https://api.z.ai/api/monitor/usage/quota/limit
Authorization: <raw-api-key>      # NOT "Bearer ..." — just the key
Content-Type: application/json
```

Live response shape (captured 2026-04-18 from the user's pro plan):

```json
{
  "code": 200, "success": true, "msg": "Operation successful",
  "data": {
    "level": "pro",
    "limits": [
      {"type": "TOKENS_LIMIT", "unit": 3, "number": 5,
       "percentage": 15, "nextResetTime": 1776519854629},
      {"type": "TOKENS_LIMIT", "unit": 6, "number": 1,
       "percentage": 32, "nextResetTime": 1776852987997},
      {"type": "TIME_LIMIT",   "unit": 5, "number": 1,
       "usage": 1000, "currentValue": 5, "remaining": 995, "percentage": 1,
       "nextResetTime": 1778235387998,
       "usageDetails": [{"modelCode":"search-prime","usage":3}, ...]}
    ]
  }
}
```

Unit mapping (observed):
- `TOKENS_LIMIT unit=3` → **5-hour rolling window** (resets every few hours)
- `TOKENS_LIMIT unit=6` → **weekly window** (resets ~7 days out)
- `TIME_LIMIT` → **MCP search calls quota** (1000/month on pro)

Working jq reference implementation in `~/.local/bin/zai-usage-bar` (keep as migration source).

## Target architecture

```
coding-plans-waybar/
├── bin/
│   ├── coding-plans-bar          # merges all enabled providers → waybar JSON
│   ├── coding-plans-popup        # GTK4 popover, one card per provider
│   ├── coding-plans-statusline   # Claude-statusline chaining (keep from upstream)
│   └── coding-plans-today        # Claude ccusage backfill (keep from upstream)
├── lib/
│   └── providers/
│       ├── __init__.py           # registry + loader
│       ├── base.py               # Protocol + PlanStatus dataclass
│       ├── claude.py             # reads state.json (ported from upstream)
│       └── zai.py                # HTTP polling (ported from zai-usage-bar)
├── share/
│   ├── config/config.toml.example
│   ├── waybar/module.jsonc       # single custom/coding-plans entry
│   ├── waybar/style.css          # #custom-coding-plans.{classes}
│   └── systemd/
│       ├── coding-plans-today.service
│       └── coding-plans-today.timer
├── install.sh                    # idempotent, guarded-marker patching
├── uninstall.sh
└── README.md
```

### Provider protocol

```python
# lib/providers/base.py
from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class PlanStatus:
    provider_id: str                   # "claude", "zai"
    display_name: str                  # "Claude", "Z.AI"
    icon: str                          # nerd-font glyph; "", ""
    short_pct: float | None            # 5-hour window %, 0–100; None if N/A
    weekly_pct: float | None
    resets_short_ms: int | None        # epoch ms of next 5h reset
    resets_weekly_ms: int | None
    plan_tier: str | None              # "pro", "max", "free", etc.
    status_class: str                  # fresh | stale | critical | exhausted | empty
    extra_rows: list[tuple[str, str]] = field(default_factory=list)
    error: str | None = None           # if set, provider failed; renderer shows stale

class Provider(Protocol):
    id: str
    display_name: str
    icon: str
    def fetch(self, config: dict) -> PlanStatus: ...
```

### Bar label format (configurable)

Default format string in `config.toml`:

```toml
[display]
bar_format = "{icon} {short_pct}%·{weekly_pct}%"
join = "  "     # between providers
show_empty_providers = false
```

Rendered example (Claude 4%/12%, Z.AI 15%/32%):

```
  4%·12%    15%·32%
```

Status class aggregation: take the worst class across enabled providers (`exhausted` > `critical` > `stale` > `fresh` > `empty`).

### Tooltip

Each provider gets its own block (same visual style upstream uses for Claude), separated by a divider line. Click anywhere on the module → `coding-plans-popup`, which renders one Adwaita card per provider.

### Config file

`~/.config/coding-plans/config.toml`:

```toml
[display]
bar_format = "{icon} {short_pct}%·{weekly_pct}%"
join = "  "
refresh_seconds = 15

[thresholds]
critical = 80
exhausted = 95

[providers.claude]
enabled = true
# Inherits all existing claude-usage settings (state_path, statusline chaining, ccusage)
state_path = "~/.cache/coding-plans/state.json"
chained_command = ""     # filled in by install.sh if existing statusLine detected

[providers.zai]
enabled = true
api_key_file = "~/.config/coding-plans/zai-key"   # chmod 600
endpoint = "https://api.z.ai/api/monitor/usage/quota/limit"
```

### Installer contract

`install.sh` goals (idempotent, marker-guarded like upstream):

1. Copy bins to `~/.local/bin/`.
2. Copy shared assets to `~/.local/share/coding-plans-waybar/`.
3. Seed `~/.config/coding-plans/config.toml` if missing.
4. Migrate from upstream if detected:
   - Detect `~/.config/claude-usage/config.toml` → copy provider settings into new config.
   - Detect `~/.config/claude-usage/zai-key` → copy to `~/.config/coding-plans/zai-key`.
   - Offer to remove old `claude-usage-*` bins + systemd timer.
5. Register Claude statusLine in `~/.claude/settings.json` (same chaining logic as upstream).
6. Install + enable user systemd timer for Claude ccusage backfill.
7. Patch `~/.config/waybar/config.jsonc` **if it exists**; otherwise print a clear snippet the user pastes into their theme config (our user's case — `bennyzen/config`).
8. Remove old `custom/claude-usage` + `custom/zai-usage` entries from `bennyzen/config` (marker-guarded) and add the unified `custom/coding-plans`.
9. Reload waybar (SIGUSR2).

## Build sequence (for the builder session)

Each step should leave the widget in a working state that can be tested end-to-end.

1. **Clone upstream** `infiniV/claude-usage-waybar` into `/tmp/upstream-claude-usage-waybar` for reference. This fork starts from scratch in `~/repos/coding-plans-waybar/` but borrows files verbatim where appropriate. Add an `UPSTREAM.md` attributing and diffing.

2. **Scaffold skeleton.** Create the directory tree above. Stub all bins with a shebang + "not yet" message. Commit.

3. **Port Claude provider.**
   - Copy upstream `claude-usage-bar` logic into `lib/providers/claude.py:fetch()`.
   - Copy `claude-usage-today` into `bin/coding-plans-today` with only the binary name changed.
   - Copy `claude-usage-statusline` into `bin/coding-plans-statusline` unchanged except paths.
   - State file moves: `~/.cache/claude-usage/state.json` → `~/.cache/coding-plans/state.json`.

4. **Build `coding-plans-bar`** that only renders Claude (no Z.AI yet). Verify output matches upstream byte-for-byte modulo the module name.

5. **Port Z.AI provider.**
   - Translate `~/.local/bin/zai-usage-bar` (bash+jq) into `lib/providers/zai.py:fetch()`.
   - Use `requests` or `urllib.request` — no new dependency beyond stdlib if possible.
   - Return `PlanStatus` with `short_pct=unit3.percentage`, `weekly_pct=unit6.percentage`, `plan_tier=data.level`, MCP quota as an `extra_row`.

6. **Multi-provider rendering** in `coding-plans-bar`:
   - Iterate `[providers.*]` sections with `enabled=true`.
   - Fetch each (guarded with try/except → PlanStatus.error).
   - Apply `bar_format` per provider, join, emit combined tooltip (Claude-block + divider + Z.AI-block).
   - Aggregate `status_class`.

7. **Popover multi-provider layout.**
   - Upstream renders a single Adwaita card with 4 rows (5h, weekly, today, session).
   - Target: one `AdwPreferencesGroup` per enabled provider, each with the rows that provider actually supplies. Provider-specific fields go in `extra_rows`.

8. **Installer.** Write `install.sh` from scratch modelled on upstream's style (colored step/ok/warn/fail helpers, `--dry-run`, marker-guarded edits). Include migration from `claude-usage-waybar`.

9. **Uninstaller** removes everything and restores the original statusLine from `chained_command`.

10. **Bennyzen wiring.** On the target machine, replace the existing two modules in `~/.config/waybar/themes/bennyzen/config`:
    - Remove `"custom/claude-usage"` block and its entry in `modules-right`.
    - Remove `"custom/zai-usage"` block and its entry in `modules-right`.
    - Add `"custom/coding-plans"` block and `"custom/coding-plans"` in `modules-right` (position: same spot the current `custom/claude-usage` holds — between `custom/exit` and `clock`).
    - Replace the appended `#custom-claude-usage.*` and `#custom-zai-usage.*` CSS blocks with `#custom-coding-plans.*`.

11. **Test matrix** before declaring done:
    - Claude only enabled → behaviour matches upstream.
    - Z.AI only enabled → matches current `zai-usage-bar` output.
    - Both enabled → combined bar label, combined tooltip, aggregate class.
    - Z.AI API down → widget stays alive, Z.AI section shows stale, Claude section unaffected.
    - Popover opens on click, renders both cards.
    - Systemd timer runs on schedule and updates today's Claude numbers.

## Decisions to confirm before building

The user explicitly invited questions. Flag these in the first reply of the build session:

1. **Name.** `coding-plans-waybar` — accept, or rename?
2. **Bar format.** Default ` 4%·12%   15%·32%` (icon + 5h·weekly per provider). Alternatives: single worst-% per provider, or text-only `C 4/12  Z 15/32`.
3. **Stubs for future providers.** v1 ships Claude + Z.AI concrete. Do we pre-stub `moonshot.py`, `qwen.py`, `dashscope.py` as NotImplementedError skeletons, or leave that for when needed?
4. **Migration aggression.** Should `install.sh` auto-remove the old `claude-usage-waybar` and `zai-usage-bar` (with backup), or require `--migrate` flag?
5. **Config path.** `~/.config/coding-plans/` — accept, or keep `~/.config/claude-usage/` to ease migration?
6. **Popover rewrite vs extend.** Upstream's popup is ~1000 lines of GTK4. Cheaper to extend (add a provider loop around the existing rendering) than rewrite. OK to accept more coupling for v1?

## Working references (preserve across sessions)

- Z.AI endpoint: `GET https://api.z.ai/api/monitor/usage/quota/limit`
- Z.AI auth: `Authorization: <raw-key>` (no `Bearer`)
- User's Z.AI key file: `~/.config/claude-usage/zai-key` (migrate to `~/.config/coding-plans/zai-key`)
- Working shell+jq prototype: `~/.local/bin/zai-usage-bar`
- Upstream reference: `https://github.com/infiniV/claude-usage-waybar`
- Multi-provider CLI prior art for usage stats (not waybar): `opencode-mystatus` (`https://github.com/vbgate/opencode-mystatus`) — their `plugin/lib/zhipu.ts` is the authoritative source on the Z.AI endpoint contract.
- Target theme: `~/.config/waybar/themes/bennyzen/config` and `bennyzen/style.css`
- Waybar reload hook after changes: `~/.config/waybar/launch.sh` (bennyzen theme script).
