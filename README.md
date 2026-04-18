# coding-plans-waybar

A single Waybar widget showing usage across multiple AI coding-plan subscriptions in one bar module.

Soft-forked from [infiniV/claude-usage-waybar](https://github.com/infiniV/claude-usage-waybar) (Claude-only) and extended with a pluggable provider system.

**Status:** v1 — Claude + Z.AI both live. See [PLAN.md](PLAN.md) for the design, [UPSTREAM.md](UPSTREAM.md) for what was borrowed from the Claude-only upstream, and [PROVIDERS.md](PROVIDERS.md) for how to add a third provider.

## v1 providers

- **Claude** (Anthropic) — via Claude Code statusLine + `ccusage` (same as upstream)
- **Z.AI** (Zhipu GLM Coding Plan) — via `/api/monitor/usage/quota/limit`

## Install

```bash
git clone https://github.com/bennyzen/coding-plans-waybar
cd coding-plans-waybar
./install.sh              # fresh install; --dry-run to preview
```

The installer copies the bins to `~/.local/bin/`, the Python package to `~/.local/share/coding-plans-waybar/lib/`, seeds `~/.config/coding-plans/config.toml`, patches your Waybar config with a guarded `custom/coding-plans` block, registers the Claude Code statusLine (chaining any previous one), and enables a 5-minute `ccusage` backfill timer.

If your Waybar config isn't at `~/.config/waybar/config.jsonc` (Omarchy/ML4W setups usually use a per-theme file), set `WAYBAR_CONFIG=/path/to/config` and `WAYBAR_DIR=/path/to/dir`.

Add the Z.AI key:

```bash
echo 'sk-…' > ~/.config/coding-plans/zai-key && chmod 600 ~/.config/coding-plans/zai-key
```

Coming from upstream `claude-usage-waybar`? Run its `./uninstall.sh` first, then ours. We don't automate that migration — the upstream tool's own uninstaller is the right path.

## Uninstall

```bash
./uninstall.sh
```

Reverses everything. Keeps your `~/.config/coding-plans/` config + Z.AI key so you can re-install later.

## Why

Upstream `claude-usage-waybar` is Claude-only: it reads Claude Code's JSONL and assumes Anthropic's 5h/weekly window semantics. For users on multiple coding plans (Claude Max + Z.AI Pro, etc.), running two bar widgets side-by-side is noisy and inconsistent.

This fork introduces a `Provider` interface so a single `custom/coding-plans` module renders all enabled plans with one shared bar slot, one tooltip, and one popover.

## Not in scope

- Tracking providers that expose no usage API and have no local logs (would need web scraping).
- Billing/invoice data — just in-period quotas.
- Anything beyond Waybar. (Though the provider layer is reusable.)
