# coding-plans-waybar

A bar widget for AI coding-plan usage. One module per provider, each with its own brand icon, stats (`5h%·weekly%`) as the label. Click any module → one unified Adwaita popover with per-provider cards.

Ships for **Waybar** (brand icon via CSS `background-image`) and **Noctalia** (a plugin under [`noctalia/`](noctalia/)).

Soft-forked from [infiniV/claude-usage-waybar](https://github.com/infiniV/claude-usage-waybar) (Claude-only) and extended with a pluggable provider system.

![config.toml on the left, the per-provider tooltip blocks on the right](example1.webp)

## v1 providers

- **Claude** (Anthropic) — via Claude Code statusLine + `ccusage`
- **Z.AI** (Zhipu GLM Coding Plan) — via `/api/monitor/usage/quota/limit`

Adding a third provider is two files. See [PROVIDERS.md](PROVIDERS.md).

## Install

```bash
git clone https://github.com/bennyzen/coding-plans-waybar
cd coding-plans-waybar
./install.sh
```

The installer:

1. Copies `coding-plans-{bar,popup,statusline,today}` to `~/.local/bin/`.
2. Copies the Python package + each provider's SVG + patcher helpers to `~/.local/share/coding-plans-waybar/`.
3. Seeds `~/.config/coding-plans/config.toml` with every provider enabled.
4. **Generates `custom/coding-plans-<id>` blocks into your Waybar config** — one per enabled provider — along with matching CSS that carries the SVG as a `background-image`. Everything is guarded by `// >>> coding-plans-waybar >>>` markers so a re-run replaces the block cleanly.
5. Registers a Claude Code `statusLine.command` (chaining any previous one).
6. Enables a 5-min systemd user timer for the `ccusage` backfill.
7. Reloads Waybar.

Custom Waybar config path? Set `WAYBAR_CONFIG=/path/to/config` (and optionally `WAYBAR_DIR=/path/to/dir` if `style.css` is co-located). The installer auto-probes `config`, `config.jsonc`, and `config.json`.

### Agent-ready config

Once installed, **the only file you edit is `~/.config/coding-plans/config.toml`**. Toggle providers on or off; re-run `./install.sh` to regenerate the Waybar module blocks. Minimal config:

```toml
[providers.claude]
enabled = true

[providers.zai]
enabled = true
# api_key_file = "~/.config/coding-plans/zai-key"   # default — chmod 600
```

### Z.AI API key

```bash
echo 'sk-…' > ~/.config/coding-plans/zai-key && chmod 600 ~/.config/coding-plans/zai-key
```

(The installer auto-migrates an existing `~/.config/claude-usage/zai-key` from upstream if you had one.)

### Coming from upstream `claude-usage-waybar`?

Run its `./uninstall.sh` first, then ours. We deliberately don't automate that migration.

## Styling

Waybar only — Noctalia capsules follow the shell's own theme and are configured
per capsule in Settings, not here.

Every visual knob is a TOML key under `[style]` (global) or `[providers.<id>.style]` (per-provider override). Change a value, re-run `./install.sh`, done. Your overrides land in the generated CSS verbatim:

```toml
[style]
font_family      = ""             # "" = inherit from the bar
font_size        = "11px"
letter_spacing   = "0.02em"
padding          = "0 8px 0 23px" # room on the left for the icon
margin           = "0 3px"
icon_size        = "13px"
icon_position    = "6px center"
icon_bg_color    = ""             # e.g. "#ffffff" — disc behind the icon
icon_bg_padding  = "2px"          # ring width around the icon
border_radius    = ""             # e.g. "10px" for a pill shape
color            = "@foreground"  # uses the active Waybar theme's var

fresh_opacity    = 1.0            # dims the whole module (icon + disc + text)
stale_opacity    = 0.4
empty_opacity    = 0.28
critical_color   = "#c9a227"
exhausted_color  = "#d24646"
critical_weight  = "700"
exhausted_weight = "700"

# Per-provider override — bump Claude's icon a bit larger:
[providers.claude.style]
icon_size = "15px"

# Per-provider override — white disc behind just the Z.AI glyph:
[providers.zai.style]
icon_bg_color = "#ffffff"
```

## Noctalia

[Noctalia](https://noctalia.dev) is a Quickshell-based Wayland shell with its own
plugin system, so the Waybar module cannot be reused as-is. `noctalia/` holds a
plugin that drives the same CLI.

It stays thin: `coding-plans-bar --provider <id>` remains the source of truth.
The plugin reads that JSON, uses `text` as the capsule label, maps `class` to a
theme color role, and on left click launches `coding-plans-popup` — the same GTK
popover Waybar users get.

`install.sh` does **not** touch Noctalia. Register this directory as a path-type
plugin source and enable it:

```bash
noctalia msg plugins source add coding-plans path "$PWD/noctalia"
noctalia msg plugins enable bennyzen/coding-plans
```

Then add the widget to a bar in Settings → Bar. One capsule shows one provider;
add a second instance and set each one's `provider` for a second.

### Per-capsule settings

| Key | Default | What |
|---|---|---|
| `provider` | `claude` | provider id, as in `config.toml` |
| `icon_path` | *(empty)* | explicit icon file; empty auto-detects the brand SVG |
| `glyph` | `brain` | Tabler icon name, used only when no SVG resolves |
| `show_glyph` | `true` | the icon beside the reading |
| `show_name` | `false` | the provider id next to the percentages |
| `refresh_minutes` | `5` | minutes between readings |

Icons resolve from the installed tree, preferring `<id>-color.svg` over the mono
`<id>.svg` before falling back to the icon font. An installed tree can predate a
checkout that added a colour variant — re-run `./install.sh` if a capsule shows
the mono icon.

Noctalia does not render Pango, so the tooltip markup is stripped and emitted one
row per line.

The plugin loads directly from this checkout, so editing `bar.luau` hot-reloads.
`plugin.toml` does not: adding or renaming a setting needs `plugins disable` then
`enable`, or the shell logs `read undeclared setting '<key>'`.

## Layout

```
~/.local/bin/
├── coding-plans-bar          — Waybar exec (accepts --provider <id>)
├── coding-plans-popup        — GTK4 Adwaita popover
├── coding-plans-statusline   — Claude Code statusLine handler
└── coding-plans-today        — ccusage backfill (bash+jq)

~/.local/share/coding-plans-waybar/
├── lib/coding_plans/         — Python package
│   └── providers/
│       ├── <id>.py           — per-provider module (fetch + hooks)
│       └── icons/             — per-provider brand SVGs (<id>.svg mono + <id>-color.svg baked; see PROVIDERS.md)
├── icons/                    — flat copy of provider SVGs + any generated disc-<color>.svg backdrops
├── _generate_waybar.py       — reads config.toml, emits module + style blocks
├── _patch_waybar.py          — installs/uninstalls guarded Waybar block
├── _patch_style.py           — installs/uninstalls guarded style.css block
└── _patch_toml.py            — safe TOML edits for chained_command

~/.config/coding-plans/config.toml
~/.cache/coding-plans/state.json     — shared state, keyed by provider id
```

`noctalia/` is not installed anywhere: the shell loads that plugin from this
checkout via a path-type source. See [Noctalia](#noctalia).

## Uninstall

```bash
./uninstall.sh
```

Reverses everything. Keeps `~/.config/coding-plans/` and your Z.AI key for a future re-install.

## Development / tests

```bash
python3 -m venv --system-site-packages .pytest_venv
.pytest_venv/bin/pip install pytest
.pytest_venv/bin/python -m pytest tests/ -q
```

32 tests: provider fetches, bar rendering, installer patcher roundtrip, waybar generator.

## Attribution

- Upstream: [infiniV/claude-usage-waybar](https://github.com/infiniV/claude-usage-waybar) — what was borrowed is catalogued in [UPSTREAM.md](UPSTREAM.md).
- Brand SVGs: [@lobehub/icons](https://lobehub.com/icons) (MIT).
