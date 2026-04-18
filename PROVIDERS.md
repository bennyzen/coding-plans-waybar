# Adding a provider

A provider is a Python module in `lib/coding_plans/providers/` that tells the bar + popup how to fetch usage for a given AI coding-plan service. v1 ships two: Claude and Z.AI. This doc shows how to add a third.

## The contract

Every provider exposes a module-level object named `PROVIDER` that satisfies the [`Provider`](lib/coding_plans/providers/base.py) protocol:

```python
class Provider(Protocol):
    id: str              # slug used as the config section name ("claude", "zai", ...)
    display_name: str    # shown in the popup header ("Claude")
    icon: str            # nerd-font glyph; "" for none

    def fetch(self, config: dict) -> PlanStatus: ...
```

`fetch()` MUST NOT raise. Any error (missing credentials, API down, bad response) must return a `PlanStatus` with `status_class="stale"` and a short human-readable `error` string. The bar + popup treat `error` as a signal to render the stale tag; they don't surface the string itself in the bar label, but they print it in the tooltip and the popup card's error row.

## `PlanStatus`

```python
@dataclass
class PlanStatus:
    provider_id: str              # same as PROVIDER.id
    display_name: str
    icon: str

    short_pct: int | None = None      # 5-hour window, 0–100
    weekly_pct: int | None = None     # 7-day window, 0–100
    resets_short_ms: int | None = None   # epoch ms
    resets_weekly_ms: int | None = None

    plan_tier: str | None = None          # "pro", "max", "free", ...
    status_class: str = "empty"           # fresh | stale | critical | exhausted | empty

    extra_rows: list[tuple[str, str]] = []   # (label, value) pairs — used if
                                             # tooltip_extras()/build_popup_rows()
                                             # aren't defined.
    details: dict[str, Any] = {}             # provider-specific payload for
                                             # per-provider popup rendering.
    error: str | None = None
```

## Optional hooks

| Hook | Return | Purpose |
|---|---|---|
| `tooltip_extras(plan, cfg, palette) -> list[str]` | Pango-markup lines | Extra rows in the Waybar hover tooltip, after the standard 5H/WEEKLY rows. Claude: TODAY + SESSION. Z.AI: MCP QUOTA. |
| `build_popup_rows(plan, cfg, palette) -> list[Gtk.Widget]` | Gtk widgets | Extra widgets in the popup card, after the standard 5H/WEEKLY MetricRows. Imports GTK lazily so the bar/statusline don't pull in PyGObject. |

Both are optional. A provider that supplies only `fetch()` gets the standard two-row bar/popup card with no extras.

## Minimal example: `foo.py`

```python
# lib/coding_plans/providers/foo.py
"""Foo provider — demo, reads a single file for usage."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from .base import PlanStatus


class FooProvider:
    id = "foo"
    display_name = "Foo"
    icon = "󰒪"

    def fetch(self, config: dict[str, Any]) -> PlanStatus:
        providers = config.get("providers") or {}
        foo_cfg = providers.get(self.id) or {}
        path = Path(foo_cfg.get("usage_file") or "/tmp/foo-usage")

        if not path.exists():
            return PlanStatus(
                provider_id=self.id,
                display_name=self.display_name,
                icon=self.icon,
                status_class="stale",
                error=f"no usage file at {path}",
            )

        pct = int(path.read_text().strip())
        thresholds = config.get("thresholds") or {}
        critical = int(thresholds.get("critical", 80))
        exhausted = int(thresholds.get("exhausted", 100))
        cls = "exhausted" if pct >= exhausted else "critical" if pct >= critical else "fresh"

        return PlanStatus(
            provider_id=self.id,
            display_name=self.display_name,
            icon=self.icon,
            short_pct=pct,
            status_class=cls,
        )


PROVIDER = FooProvider()
```

And the config:

```toml
# ~/.config/coding-plans/config.toml
[providers.foo]
enabled = true
usage_file = "~/.cache/foo/usage"
```

That's it. No registry edits, no install-time handshake. The `load_enabled()` loader in `lib/coding_plans/providers/__init__.py` iterates every `[providers.*]` section in config and dynamically imports the matching module.

## Testing

Put a file under `tests/test_<id>_provider.py`. The repo's existing `test_claude_provider.py` and `test_zai_provider.py` are the canonical patterns:

- Use the `xdg` fixture (from `tests/conftest.py`) to isolate XDG paths.
- Mock any outbound HTTP via `unittest.mock.patch.object(mod.urllib.request, "urlopen", ...)`. Providers that hit the network must have a cache and must handle `urllib.error.URLError` → stale+error.
- Cover: happy-path (fresh), threshold cross (critical/exhausted), missing credentials, network error, non-200 API.

Run with:

```bash
python3 -m venv --system-site-packages .pytest_venv
.pytest_venv/bin/pip install pytest
.pytest_venv/bin/python -m pytest tests/ -q
```

## Stateful vs stateless providers

- **Stateless** (like Z.AI) — `fetch()` hits a live API every tick. Cache responses in-process against a short TTL (Z.AI uses 10s) so the popup's 1s refresh doesn't DDoS the upstream.
- **Stateful** (like Claude) — `fetch()` reads from `~/.cache/coding-plans/state.json` under `providers.<id>`. Some external process populates that slice (e.g. a statusline command, a systemd-timer-driven backfill). Use `coding_plans.state.load_state()` + `provider_state()` + `set_provider_state()` + `write_state()` — writes are atomic (temp file + rename).

## Icons

- Use a glyph that's present in **Nerd Font** (the repo's default). Providers without an obvious glyph in the font can use a generic one like `` (brain) or `` (plug).
- `icon` becomes the `{icon}` placeholder in the user's `bar_format`. Keep it to a single glyph so the bar doesn't expand every tick.

## Not supported in v1

- Per-provider bar segments with a different `bar_format`. v1 applies one global format to every provider's segment, with the provider's `icon`/`plan_tier`/`display_name` substituted in.
- Providers that refresh their own rendering asynchronously. The bar polls at Waybar's configured interval (default 15s); the popup polls at 1s. Providers must be safe to `fetch()` at either cadence.
