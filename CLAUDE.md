# Agent brief

Read this before touching install behaviour. Human-facing tour: `README.md`.
This file is the short list of things that have bitten agents (and committers)
in the past — keep it tight.

## What install.sh touches outside this repo

| Path | What lands |
|---|---|
| `~/.local/bin/coding-plans-{bar,popup,statusline,today}` | the four CLIs |
| `~/.local/share/coding-plans-waybar/` | Python pkg + share assets + icons |
| `~/.config/coding-plans/config.toml` | seeded from `share/config/config.toml.example` only if missing |
| `~/.config/waybar/<config>.jsonc` | marker-guarded module block + `modules-right` entries |
| `~/.config/waybar/<style>.css` | marker-guarded styling block |
| `~/.claude/settings.json` | `statusLine.command` rewritten; any pre-existing one is chained via config.toml |
| `~/.config/systemd/user/coding-plans-today.{service,timer}` | enabled user timer |

Every external edit is bracketed by `>>> coding-plans-waybar >>>` / `<<<`
markers in whatever comment style the file uses (`//`, `#`, `/* */`).
**Never hand-edit between markers** — `./install.sh` regenerates them and
`./uninstall.sh` strips by them.

## Footguns

1. **Waybar's `exec` runs in the launcher's PATH, not your shell's.**
   ML4W/Omarchy/Hyprland launchers typically don't add `~/.local/bin`. The
   generator emits absolute paths (`{bin_dir}/coding-plans-bar` and
   `{bin_dir}/coding-plans-popup`); don't strip them when refactoring.
   Regression test: `tests/test_generate_waybar.py::test_module_uses_absolute_bin_paths`.

2. **Z.AI's `Authorization` header is the raw key, no `Bearer ` prefix.**
   See `lib/coding_plans/providers/zai.py:73`. Adding `Bearer ` causes silent
   401s that surface as a stale module — easy to misdiagnose.

3. **Active waybar config is rarely at `~/.config/waybar/config{,.json,.jsonc}`.**
   ML4W/Omarchy/per-theme setups stash it under `themes/<name>/…`.
   `install.sh` first probes `pgrep -axa waybar` for `-c`/`-s` (and
   `--config=`/`--style=`), then falls back to static paths under
   `$WAYBAR_DIR`. Honour that order if you add code that needs to know
   the active config.

4. **Migration from upstream `claude-usage-waybar` is intentionally manual.**
   `install.sh` does *not* strip the user's pre-existing `custom/claude-usage`
   waybar entry. Silently editing somebody's bar is worse than telling them
   to run `uninstall.sh` from the upstream project.

## Override env vars install.sh honours

`BIN_DIR` `SHARE_DIR` `CFG_DIR` `CACHE_DIR` `WAYBAR_DIR` `WAYBAR_CONFIG`
`WAYBAR_STYLE` `CLAUDE_SETTINGS` `SYSTEMD_DIR` `CODING_PLANS_INSERT_AFTER`

`CODING_PLANS_INSERT_AFTER=<module_name>` anchors new entries after a
specific existing module in `modules-right`; useful when retrofitting.

## Verify an install actually works (don't trust your shell)

```bash
# Reproduce waybar's PATH and run the bar there — same env it'll use:
WAYBAR_PATH=$(tr '\0' '\n' < /proc/$(pgrep -x waybar)/environ | grep ^PATH= | cut -d= -f2-)
env -i PATH="$WAYBAR_PATH" HOME="$HOME" sh -c 'coding-plans-bar --provider zai'

# Find the active config + style:
pgrep -axa waybar
```

If the bar command works in your shell but not under waybar's PATH, the
emitted module is using a bare invocation — see footgun #1.

## Map of the moving parts

- `bin/` — the four CLIs the user calls; thin entry points into `lib/`
- `lib/coding_plans/` — provider modules (`providers/<id>.py`) + UI code
- `share/_generate_waybar.py` — emits per-provider module + style snippets from config.toml
- `share/_patch_waybar.py` / `_patch_style.py` / `_patch_toml.py` — marker-guarded patchers
- `share/config/config.toml.example` — seed config; canonical reference for tunable keys

Adding a new provider: see `PROVIDERS.md` (it's the contract).

## Tests

```bash
python3 -m venv --system-site-packages .pytest_venv && \
  .pytest_venv/bin/pip install pytest && \
  .pytest_venv/bin/python -m pytest tests/ -q
```

The lib package is loaded onto `sys.path` by `tests/conftest.py`; the
`share/` scripts are loaded via `importlib.util.spec_from_file_location`
because they aren't an installed package.
