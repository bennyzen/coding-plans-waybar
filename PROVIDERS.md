# Adding a provider

A provider is a Python module in `lib/coding_plans/providers/` that tells the bar + popup how to fetch usage for a given AI coding-plan service. v1 ships two: Claude and Z.AI.

**Adding a new provider is two files:**

1. `lib/coding_plans/providers/<id>.py` — the provider module.
2. `lib/coding_plans/providers/icons/<id>.svg` — the brand SVG (MIT/public-domain; grab from [lobehub.com/icons](https://lobehub.com/icons) for anything AI-shaped).

Then add `[providers.<id>]` to `~/.config/coding-plans/config.toml` with `enabled = true`. That's it — no registry edits, no font rebuild.

## The contract

Every provider exposes a module-level object named `PROVIDER` that satisfies the [`Provider`](lib/coding_plans/providers/base.py) protocol:

```python
class Provider(Protocol):
    id: str                     # slug used as the config section name ("claude", "zai")
    display_name: str           # shown in the bar label + popup header ("Claude")
    icon_path: Path | None      # Path to the brand SVG — ships at providers/icons/<id>.svg.
                                # The popup renders it natively. None = no brand icon.
    icon_color: str | None      # Hex colour for the bar label text (e.g. Claude's #D97757).
                                # None = inherits the active theme's foreground.

    def fetch(self, config: dict) -> PlanStatus: ...
```

**Where each field shows up:**

- **Bar label** — `display_name` rendered in `icon_color` (if set). Waybar's text is Pango, which can't embed SVGs, so the bar uses coloured text as the brand mark.
- **Popup card** — `icon_path`'s SVG is rendered via `Gtk.Image` in the card header, tinted by the GTK theme when the SVG uses `fill="currentColor"` or hard-coded when it carries its own colour.
- **Tooltip header** — `display_name` in monochrome (the tooltip is also Pango).

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

from pathlib import Path
from typing import Any

from .base import PlanStatus


class FooProvider:
    id = "foo"
    display_name = "Foo"
    icon_path = Path(__file__).parent / "icons" / "foo.svg"
    icon_color = "#6B9BD1"  # brand blue, or None to skip tinting

    def fetch(self, config: dict[str, Any]) -> PlanStatus:
        providers = config.get("providers") or {}
        foo_cfg = providers.get(self.id) or {}
        path = Path(foo_cfg.get("usage_file") or "/tmp/foo-usage")

        if not path.exists():
            return PlanStatus(
                provider_id=self.id,
                display_name=self.display_name,
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
            short_pct=pct,
            status_class=cls,
        )


PROVIDER = FooProvider()
```

Drop `foo.svg` at `lib/coding_plans/providers/icons/foo.svg` and you're done.

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

- Source: [lobehub.com/icons](https://lobehub.com/icons) — MIT-licensed SVGs for every major AI provider. Grab the mono form (`{id}.svg`, uses `currentColor`) and the color form (`{id}-color.svg`, brand palette baked in) and ship whichever fits the visual you want in the popup card.
- Put the SVG at `lib/coding_plans/providers/icons/<id>.svg` (or `<id>-color.svg` — the filename just has to match what `icon_path` points at).
- `icon_color` drives the bar label colour only. The popup reads the SVG directly.

## Not supported in v1

- Per-provider bar segments with a different `bar_format`. v1 applies one global format to every provider's segment, with the provider's `{brand}`/`{display_name}`/`{short_pct}`/`{weekly_pct}`/`{plan_tier}` substituted in.
- Providers that refresh their own rendering asynchronously. The bar polls at Waybar's configured interval (default 15s); the popup polls at 1s. Providers must be safe to `fetch()` at either cadence.
- **SVG icons in the bar label** — Waybar's label is Pango text, which can't embed SVGs. The brand mark in the bar is `display_name` tinted by `icon_color`; the SVG shows in the popup and tooltip header. If you need pictorial icons in the bar, fork into a multi-module layout (one `custom/coding-plans-<id>` per provider, with CSS `background-image: url(...)`).
