# coding-plans-waybar

A single Waybar widget showing usage across multiple AI coding-plan subscriptions in one bar module.

Soft-forked from [infiniV/claude-usage-waybar](https://github.com/infiniV/claude-usage-waybar) (Claude-only) and extended with a pluggable provider system.

**Status:** planning. See [PLAN.md](PLAN.md).

## v1 providers

- **Claude** (Anthropic) — via Claude Code statusLine + `ccusage` (same as upstream)
- **Z.AI** (Zhipu GLM Coding Plan) — via `/api/monitor/usage/quota/limit`

## Why

Upstream `claude-usage-waybar` is Claude-only: it reads Claude Code's JSONL and assumes Anthropic's 5h/weekly window semantics. For users on multiple coding plans (Claude Max + Z.AI Pro, etc.), running two bar widgets side-by-side is noisy and inconsistent.

This fork introduces a `Provider` interface so a single `custom/coding-plans` module renders all enabled plans with one shared bar slot, one tooltip, and one popover.

## Not in scope

- Tracking providers that expose no usage API and have no local logs (would need web scraping).
- Billing/invoice data — just in-period quotas.
- Anything beyond Waybar. (Though the provider layer is reusable.)
