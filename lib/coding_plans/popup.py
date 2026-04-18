"""coding-plans-waybar — multi-provider popup.

Aesthetic: IBM-ish terminal diagnostic. Monospace, hairline rules, bracket
tokens as icons, one accent that deepens as limits approach. Reads the
current Omarchy theme at startup so colours follow whatever the user is
running (IBM, Tokyo Night, Gruvbox…). Falls back to a baked palette if
omarchy isn't present.

Multi-provider layout: one ``cp-card`` per enabled provider, stacked
vertically. Each card renders a header (brand + optional plan-tier chip +
status tag), the 5-HOUR and WEEKLY metric rows shared by all providers,
then provider-specific extras via ``providers.<id>.build_popup_rows()``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

# gtk4-layer-shell must be dlopened BEFORE libwayland so our popover anchors
# under the waybar icon. Re-exec with LD_PRELOAD if we haven't already.
#
# Only re-exec when this module was launched as a script (``python3 popup.py``
# or via the ``coding-plans-popup`` shim). Importing the module via ``-c`` or
# ``python -m`` — common from test harnesses — sets ``sys.argv[0]`` to a
# sentinel like ``-c`` which we can't re-exec blindly.
def _maybe_preload() -> None:
    if os.environ.get("_CODING_PLANS_POPUP_PRELOADED"):
        return
    script = sys.argv[0] if sys.argv else ""
    if not script or not os.path.isfile(script):
        # Module imported in-process (e.g. ``python -c 'from coding_plans.popup
        # import main'``) — nothing we can re-exec usefully. The caller is on
        # the hook for setting LD_PRELOAD themselves if they want layer-shell.
        return
    for cand in (
        "/usr/lib/libgtk4-layer-shell.so.0",
        "/usr/lib/libgtk4-layer-shell.so",
        "/usr/lib64/libgtk4-layer-shell.so.0",
        "/usr/local/lib/libgtk4-layer-shell.so.0",
    ):
        if os.path.exists(cand):
            env = dict(os.environ)
            existing = env.get("LD_PRELOAD", "")
            env["LD_PRELOAD"] = f"{cand}:{existing}" if existing else cand
            env["_CODING_PLANS_POPUP_PRELOADED"] = "1"
            os.execve(sys.executable, [sys.executable, *sys.argv], env)


_maybe_preload()

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .config import load_config  # noqa: E402
from .formatters import (  # noqa: E402
    human_ago,
    human_cost,
    human_countdown,
    human_tokens,
    is_stale,
    reset_wall_clock,
)
from .palette import BAKED_PALETTE, load_palette  # noqa: E402,F401
from .paths import CONFIG_PATH  # noqa: E402
from .providers import load_enabled  # noqa: E402
from .providers.base import PlanStatus  # noqa: E402

PIDFILE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "coding-plans-popup.pid"


# ─── CSS ─────────────────────────────────────────────────────────────────


def build_css(palette: dict[str, str]) -> str:
    """Inject palette into the popover CSS. Kept in one place for clarity."""
    p = palette
    return f"""
@define-color cp_bg       {p['bg']};
@define-color cp_surface  {p['surface']};
@define-color cp_text     {p['text']};
@define-color cp_muted    {p['muted']};
@define-color cp_border   {p['border']};
@define-color cp_hairline alpha(@cp_text, 0.07);
@define-color cp_accent   {p['accent']};
@define-color cp_warn     {p['warn']};
@define-color cp_crit     {p['crit']};
@define-color cp_danger   {p['danger']};

window.coding-plans-popup {{
  background-color: transparent;
}}

.cp-stack {{
  background-color: transparent;
}}

.cp-card {{
  background-color: @cp_surface;
  border: 1px solid @cp_border;
  border-radius: 2px;
  padding: 18px 18px 12px 18px;
  color: @cp_text;
  font-family: "JetBrainsMono Nerd Font", "JetBrains Mono", monospace;
}}

/* Header ─────────────────────────────────────────────── */
.cp-brand {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.22em;
  color: @cp_muted;
  text-transform: uppercase;
}}
.cp-tag {{
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.22em;
  padding: 2px 8px;
  border-radius: 2px;
  background-color: alpha(@cp_accent, 0.12);
  color: @cp_accent;
  text-transform: uppercase;
  border: 1px solid alpha(@cp_accent, 0.26);
  min-height: 0;
}}
.cp-tag.idle {{
  background-color: alpha(@cp_muted, 0.10);
  color: @cp_muted;
  border-color: alpha(@cp_muted, 0.24);
}}
.cp-tag.crit {{
  background-color: alpha(@cp_warn, 0.14);
  color: @cp_warn;
  border-color: alpha(@cp_warn, 0.32);
}}
.cp-tag.over {{
  background-color: alpha(@cp_danger, 0.16);
  color: @cp_danger;
  border-color: alpha(@cp_danger, 0.4);
}}
.cp-tier {{
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.22em;
  padding: 2px 8px;
  border-radius: 2px;
  background-color: alpha(@cp_muted, 0.10);
  color: @cp_muted;
  text-transform: uppercase;
  border: 1px solid alpha(@cp_muted, 0.20);
  min-height: 0;
}}

/* Rule ───────────────────────────────────────────────── */
.cp-rule {{
  min-height: 1px;
  background-color: @cp_hairline;
  margin: 12px 0;
}}

/* Metric row ─────────────────────────────────────────── */
.cp-metric-row {{
  padding: 2px 0;
}}
.cp-bracket {{
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: @cp_muted;
  padding-right: 12px;
}}
.cp-title {{
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: @cp_text;
  text-transform: uppercase;
}}
.cp-pct {{
  font-size: 22px;
  font-weight: 700;
  font-feature-settings: "tnum";
  color: @cp_accent;
  letter-spacing: -0.01em;
}}
.cp-metric.crit .cp-pct {{ color: @cp_warn; }}
.cp-metric.over .cp-pct {{ color: @cp_danger; }}
.cp-metric.empty .cp-pct {{ color: @cp_muted; }}
.cp-metric.stale .cp-pct {{ color: alpha(@cp_text, 0.45); }}

.cp-sub {{
  font-size: 10px;
  color: @cp_muted;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-top: 6px;
  padding-left: 1px;
}}

/* Progress rail ──────────────────────────────────────── */
progressbar.cp-rail trough {{
  min-height: 2px;
  background-color: alpha(@cp_text, 0.08);
  border-radius: 0;
  border: none;
}}
progressbar.cp-rail progress {{
  min-height: 2px;
  background-color: @cp_accent;
  border-radius: 0;
  border: none;
}}
progressbar.cp-rail.crit progress {{ background-color: @cp_warn; }}
progressbar.cp-rail.over  progress {{ background-color: @cp_danger; }}
progressbar.cp-rail.empty progress {{ background-color: transparent; }}

/* Today grid ─────────────────────────────────────────── */
.cp-today-label {{
  font-size: 10px;
  letter-spacing: 0.14em;
  color: @cp_muted;
  text-transform: uppercase;
}}
.cp-today-value {{
  font-size: 15px;
  font-weight: 600;
  font-feature-settings: "tnum";
  color: @cp_text;
}}
.cp-side {{
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: @cp_muted;
  text-transform: uppercase;
}}

/* Updated timestamp ──────────────────────────────────── */
.cp-updated {{
  font-size: 10px;
  color: @cp_muted;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin-top: 4px;
}}

/* Empty / error state ─────────────────────────────────── */
.cp-empty {{
  font-size: 11px;
  color: @cp_muted;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 8px 0;
}}
.cp-error {{
  font-size: 10px;
  color: @cp_danger;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 4px 0;
}}

/* Footer ─────────────────────────────────────────────── */
.cp-footer {{
  margin-top: 8px;
  border-top: 1px solid @cp_hairline;
  padding-top: 4px;
}}
.cp-footer button {{
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 10px 12px;
  color: @cp_muted;
  font-family: "JetBrainsMono Nerd Font", "JetBrains Mono", monospace;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  box-shadow: none;
  transition: color 120ms ease;
}}
.cp-footer button:hover {{
  color: @cp_text;
  background: alpha(@cp_text, 0.03);
}}
.cp-footer .cp-vrule {{
  background-color: @cp_hairline;
  min-width: 1px;
  margin: 6px 0;
}}
"""


# ─── Layer shell + PID handling ───────────────────────────────────────────


def try_layer_shell(window: Gtk.Window) -> bool:
    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LS  # type: ignore[import-not-found]
    except (ValueError, ImportError):
        return False
    LS.init_for_window(window)
    LS.set_layer(window, LS.Layer.OVERLAY)
    LS.set_anchor(window, LS.Edge.TOP, True)
    LS.set_anchor(window, LS.Edge.RIGHT, True)
    LS.set_margin(window, LS.Edge.TOP, 34)
    LS.set_margin(window, LS.Edge.RIGHT, 10)
    LS.set_keyboard_mode(window, LS.KeyboardMode.ON_DEMAND)
    return True


def toggle_existing() -> bool:
    if not PIDFILE.exists():
        return False
    try:
        pid = int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        PIDFILE.unlink(missing_ok=True)
        return False


# ─── Safe fetch (mirrors bar._safe_fetch) ─────────────────────────────────


def _safe_fetch(provider: Any, cfg: dict[str, Any]) -> PlanStatus:
    try:
        return provider.fetch(cfg)
    except Exception as exc:  # noqa: BLE001
        return PlanStatus(
            provider_id=provider.id,
            display_name=provider.display_name,
            status_class="stale",
            error=f"fetch failed: {exc!r}",
        )


# ─── Classification helpers ───────────────────────────────────────────────


def status_tag(plan: PlanStatus, cfg: dict) -> tuple[str, str]:
    """Return (label, css_class) for the header chip of one provider."""
    pct5 = plan.short_pct
    pctW = plan.weekly_pct
    display = cfg.get("display") or {}
    thresholds = cfg.get("thresholds") or {}
    critical = int(
        display.get("critical_threshold") or thresholds.get("critical", 80)
    )
    exhausted = int(
        display.get("exhausted_threshold") or thresholds.get("exhausted", 100)
    )

    if plan.status_class == "stale":
        updated = int((plan.details or {}).get("updated_at") or 0)
        if updated:
            return (f"idle · {human_ago(updated).replace(' ago', '')}", "idle")
        return ("idle", "idle")
    if pct5 is None and pctW is None:
        return ("— —", "idle")
    worst = max((p for p in (pct5, pctW) if p is not None), default=0)
    if worst >= exhausted:
        return ("over", "over")
    if worst >= critical:
        return ("crit", "crit")
    return ("live", "")


def metric_class(pct: int | None, stale: bool, cfg: dict) -> str:
    display = cfg.get("display") or {}
    thresholds = cfg.get("thresholds") or {}
    critical = int(
        display.get("critical_threshold") or thresholds.get("critical", 80)
    )
    exhausted = int(
        display.get("exhausted_threshold") or thresholds.get("exhausted", 100)
    )
    if pct is None:
        return "empty"
    if stale:
        return "stale"
    if pct >= exhausted:
        return "over"
    if pct >= critical:
        return "crit"
    return ""


def _plan_stale(plan: PlanStatus, cfg: dict) -> bool:
    """Is this plan's most-recent data stale?

    For stateful providers (Claude) we honour ``details.updated_at`` against
    the configured window. For stateless providers (Z.AI) we key off
    ``status_class`` — if the provider returns ``stale`` it means the fetch
    failed, so visually treat it as stale.
    """
    if plan.status_class == "stale":
        return True
    updated = int((plan.details or {}).get("updated_at") or 0)
    if not updated:
        # Stateless provider (no updated_at) — only stale if status_class says so.
        return False
    stale_limit = int((cfg.get("behavior") or {}).get("stale_after_seconds", 300))
    return is_stale(updated, stale_limit)


# ─── Metric / Today / Session widgets ─────────────────────────────────────


class MetricRow(Gtk.Box):
    def __init__(self, token: str, title: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("cp-metric")

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        head.add_css_class("cp-metric-row")

        bracket = Gtk.Label(label=f"[{token}]", xalign=0.0)
        bracket.add_css_class("cp-bracket")

        title_label = Gtk.Label(label=title, xalign=0.0)
        title_label.add_css_class("cp-title")
        title_label.set_hexpand(True)
        title_label.set_valign(Gtk.Align.CENTER)

        self.pct_label = Gtk.Label(label="— %", xalign=1.0)
        self.pct_label.add_css_class("cp-pct")

        head.append(bracket)
        head.append(title_label)
        head.append(self.pct_label)
        self.append(head)

        self.bar = Gtk.ProgressBar()
        self.bar.set_fraction(0.0)
        self.bar.add_css_class("cp-rail")
        self.bar.set_margin_top(10)
        self.append(self.bar)

        self.sub = Gtk.Label(label="— —", xalign=0.0)
        self.sub.add_css_class("cp-sub")
        self.append(self.sub)

    def update(self, *, pct: int | None, sub: str, stale: bool, cfg: dict) -> None:
        cls = metric_class(pct, stale, cfg)
        for c in ("crit", "over", "empty", "stale"):
            self.remove_css_class(c)
            self.bar.remove_css_class(c)
        if cls:
            self.add_css_class(cls)
            self.bar.add_css_class(cls)

        if pct is None:
            self.pct_label.set_label("—")
            self.bar.set_fraction(0.0)
        else:
            self.pct_label.set_label(f"{pct}%")
            self.bar.set_fraction(max(0.0, min(1.0, pct / 100.0)))
        self.sub.set_label(sub)


class TodayRow(Gtk.Box):
    """Aggregated usage for the current calendar day (Claude)."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        head.add_css_class("cp-metric-row")
        bracket = Gtk.Label(label="[TD]", xalign=0.0)
        bracket.add_css_class("cp-bracket")
        title = Gtk.Label(label="TODAY", xalign=0.0)
        title.add_css_class("cp-title")
        title.set_hexpand(True)
        self.models_label = Gtk.Label(label="", xalign=1.0)
        self.models_label.add_css_class("cp-side")
        self.models_label.set_ellipsize(3)
        self.models_label.set_max_width_chars(28)
        head.append(bracket)
        head.append(title)
        head.append(self.models_label)
        self.append(head)

        grid = Gtk.Grid(column_spacing=18, row_spacing=4)
        grid.set_margin_top(10)
        for col, label in enumerate(("TOKENS", "COST")):
            lbl = Gtk.Label(label=label, xalign=0.0)
            lbl.add_css_class("cp-today-label")
            grid.attach(lbl, col, 0, 1, 1)

        self.tok_val = Gtk.Label(label="—", xalign=0.0)
        self.tok_val.add_css_class("cp-today-value")
        self.cost_val = Gtk.Label(label="—", xalign=0.0)
        self.cost_val.add_css_class("cp-today-value")
        grid.attach(self.tok_val, 0, 1, 1, 1)
        grid.attach(self.cost_val, 1, 1, 1, 1)
        self.append(grid)

    def update(self, today: dict) -> None:
        self.tok_val.set_label(human_tokens(today.get("tokens", 0) or 0))
        self.cost_val.set_label(human_cost(today.get("cost_usd", 0) or 0))
        models = today.get("models") or []
        self.models_label.set_label(" · ".join(models).upper() if models else "")


class SessionRow(Gtk.Box):
    """Snapshot of the ACTIVE Claude Code session (last statusline turn)."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        head.add_css_class("cp-metric-row")
        bracket = Gtk.Label(label="[SS]", xalign=0.0)
        bracket.add_css_class("cp-bracket")
        title = Gtk.Label(label="SESSION", xalign=0.0)
        title.add_css_class("cp-title")
        title.set_hexpand(True)
        self.model_label = Gtk.Label(label="", xalign=1.0)
        self.model_label.add_css_class("cp-side")
        self.model_label.set_ellipsize(3)
        self.model_label.set_max_width_chars(28)
        head.append(bracket)
        head.append(title)
        head.append(self.model_label)
        self.append(head)

        grid = Gtk.Grid(column_spacing=18, row_spacing=4)
        grid.set_margin_top(10)
        grid.set_column_homogeneous(True)
        for col, label in enumerate(("COST", "CONTEXT", "LINES")):
            lbl = Gtk.Label(label=label, xalign=0.0)
            lbl.add_css_class("cp-today-label")
            grid.attach(lbl, col, 0, 1, 1)
        self.cost_val = Gtk.Label(label="—", xalign=0.0)
        self.ctx_val = Gtk.Label(label="—", xalign=0.0)
        self.lines_val = Gtk.Label(label="—", xalign=0.0)
        for widget in (self.cost_val, self.ctx_val, self.lines_val):
            widget.add_css_class("cp-today-value")
        grid.attach(self.cost_val, 0, 1, 1, 1)
        grid.attach(self.ctx_val, 1, 1, 1, 1)
        grid.attach(self.lines_val, 2, 1, 1, 1)
        self.append(grid)

        self.tokens_label = Gtk.Label(xalign=0.0)
        self.tokens_label.add_css_class("cp-sub")
        self.tokens_label.set_margin_top(8)
        self.append(self.tokens_label)

    def update(self, session: dict) -> None:
        name = (session.get("model_name") or "").upper()
        self.model_label.set_label(name)
        self.cost_val.set_label(human_cost(session.get("cost_usd", 0) or 0))
        ctx_pct = session.get("context_pct")
        self.ctx_val.set_label("—" if ctx_pct is None else f"{ctx_pct}%")
        added = session.get("lines_added", 0) or 0
        removed = session.get("lines_removed", 0) or 0
        self.lines_val.set_label(f"+{added} / -{removed}")
        ti = human_tokens(session.get("input_tokens", 0) or 0)
        to_ = human_tokens(session.get("output_tokens", 0) or 0)
        self.tokens_label.set_label(f"{ti} IN  ·  {to_} OUT")


class McpQuotaRow(Gtk.Box):
    """MCP search-calls quota (Z.AI ``TIME_LIMIT``)."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("cp-metric")

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        head.add_css_class("cp-metric-row")

        bracket = Gtk.Label(label="[MCP]", xalign=0.0)
        bracket.add_css_class("cp-bracket")

        title = Gtk.Label(label="MCP QUOTA", xalign=0.0)
        title.add_css_class("cp-title")
        title.set_hexpand(True)
        title.set_valign(Gtk.Align.CENTER)

        self.pct_label = Gtk.Label(label="— %", xalign=1.0)
        self.pct_label.add_css_class("cp-pct")

        head.append(bracket)
        head.append(title)
        head.append(self.pct_label)
        self.append(head)

        self.bar = Gtk.ProgressBar()
        self.bar.set_fraction(0.0)
        self.bar.add_css_class("cp-rail")
        self.bar.set_margin_top(10)
        self.append(self.bar)

        self.sub = Gtk.Label(label="— —", xalign=0.0)
        self.sub.add_css_class("cp-sub")
        self.append(self.sub)

    def update(self, mcp: dict, *, cfg: dict) -> None:
        current = mcp.get("currentValue") or 0
        total = mcp.get("usage") or 0
        pct_raw = mcp.get("percentage")
        pct = int(pct_raw) if pct_raw is not None else None
        next_reset_ms = mcp.get("nextResetTime")

        cls = metric_class(pct, False, cfg)
        for c in ("crit", "over", "empty", "stale"):
            self.remove_css_class(c)
            self.bar.remove_css_class(c)
        if cls:
            self.add_css_class(cls)
            self.bar.add_css_class(cls)

        if pct is None:
            self.pct_label.set_label("—")
            self.bar.set_fraction(0.0)
        else:
            self.pct_label.set_label(f"{pct}%")
            self.bar.set_fraction(max(0.0, min(1.0, pct / 100.0)))

        if next_reset_ms:
            reset_s = int(next_reset_ms) // 1000
            reset_txt = f"RESETS · {human_countdown(reset_s).upper()}"
        else:
            reset_txt = "— —"
        self.sub.set_label(f"{current} / {total}   ·   {reset_txt}")


# ─── Per-provider card ────────────────────────────────────────────────────


class ProviderCard(Gtk.Box):
    """One ``cp-card`` box, populated from a ``PlanStatus`` each tick."""

    def __init__(self, provider: Any) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("cp-card")
        self.provider = provider

        # Header row: [svg icon] [brand] [plan-tier chip] [status tag].
        # The SVG comes from provider.icon_path (co-located with the provider
        # module). GTK's default image loader honours `fill="currentColor"`
        # when the widget has a matching CSS color, so the mono SVGs inherit
        # the theme; pre-coloured SVGs (Claude's orange) are rendered as-is.
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        icon_path = getattr(provider, "icon_path", None)
        if icon_path and Path(icon_path).is_file():
            self.icon_image = Gtk.Image.new_from_file(str(icon_path))
            self.icon_image.set_pixel_size(18)
            self.icon_image.add_css_class("cp-brand-icon")
            self.icon_image.set_valign(Gtk.Align.CENTER)
            header.append(self.icon_image)
        else:
            self.icon_image = None

        self.brand = Gtk.Label(xalign=0.0)
        self.brand.set_use_markup(True)
        self.brand.add_css_class("cp-brand")
        self.brand.set_hexpand(True)
        self.brand.set_valign(Gtk.Align.CENTER)
        self._set_brand_markup(provider.display_name.upper())

        self.tier_label = Gtk.Label(label="")
        self.tier_label.add_css_class("cp-tier")
        self.tier_label.set_valign(Gtk.Align.CENTER)
        self.tier_label.set_visible(False)

        self.tag_label = Gtk.Label(label="live")
        self.tag_label.add_css_class("cp-tag")
        self.tag_label.set_valign(Gtk.Align.CENTER)

        header.set_valign(Gtk.Align.CENTER)
        header.append(self.brand)
        header.append(self.tier_label)
        header.append(self.tag_label)
        self.append(header)
        self.append(self._make_rule())

        # Always-on 5H / WEEKLY rows.
        self.five_row = MetricRow("5H", "5-HOUR WINDOW")
        self.week_row = MetricRow("7D", "WEEKLY")
        self.append(self.five_row)
        self.append(self._make_rule())
        self.append(self.week_row)

        # Provider-specific extras. Rebuilt lazily on first refresh so the
        # provider's ``build_popup_rows()`` can return fresh widgets keyed to
        # the current PlanStatus. After that we just update in place.
        self._extras_built = False
        self._extras_widgets: list[Gtk.Widget] = []
        self._extras_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.append(self._extras_wrap)

        # UPDATED label — only meaningful for stateful providers. Rendered
        # on every card, hidden automatically when the provider has no
        # ``updated_at`` timestamp (e.g. Z.AI).
        self.updated_label = Gtk.Label(xalign=0.0, label="UPDATED —")
        self.updated_label.add_css_class("cp-updated")
        self.updated_label.set_visible(False)
        self.append(self.updated_label)

        # Error label — shown only when plan.error is set.
        self.error_label = Gtk.Label(xalign=0.0, label="")
        self.error_label.add_css_class("cp-error")
        self.error_label.set_visible(False)
        self.append(self.error_label)

    def _make_rule(self) -> Gtk.Widget:
        rule = Gtk.Box()
        rule.add_css_class("cp-rule")
        return rule

    def _set_brand_markup(self, name: str) -> None:
        # Brand: "NAME  ·  USAGE" rendered with the same letter-spaced style
        # upstream uses.
        self.brand.set_markup(
            f'<span letter_spacing="440">{name}</span>'
            '  <span foreground="#727272">·</span>  '
            '<span letter_spacing="440">USAGE</span>'
        )

    def _build_extras(self, plan: PlanStatus, cfg: dict, palette: dict) -> None:
        """Call the provider's ``build_popup_rows`` hook (if any), wrap each
        returned widget in a rule-separated stack, and attach to the card.
        Called once on first refresh — thereafter widgets update in place.
        """
        import importlib

        try:
            module = importlib.import_module(f"coding_plans.providers.{plan.provider_id}")
        except ImportError:
            module = None
        hook = getattr(module, "build_popup_rows", None) if module else None
        widgets: list[Gtk.Widget] = []
        if callable(hook):
            try:
                widgets = list(hook(plan, cfg, palette))
            except Exception:  # noqa: BLE001
                # Provider bug must not break the whole popup.
                widgets = []

        for w in widgets:
            self._extras_wrap.append(self._make_rule())
            self._extras_wrap.append(w)
        self._extras_widgets = widgets
        self._extras_built = True

    def update(self, plan: PlanStatus, cfg: dict, palette: dict) -> None:
        self._set_brand_markup(plan.display_name.upper())

        # Plan-tier chip (e.g. "pro") — Z.AI exposes this, Claude currently doesn't.
        if plan.plan_tier:
            self.tier_label.set_label(plan.plan_tier.upper())
            self.tier_label.set_visible(True)
        else:
            self.tier_label.set_visible(False)

        # Status chip.
        label, cls = status_tag(plan, cfg)
        self.tag_label.set_label(label)
        for c in ("idle", "crit", "over"):
            self.tag_label.remove_css_class(c)
        if cls:
            self.tag_label.add_css_class(cls)

        stale = _plan_stale(plan, cfg)

        # 5H / WEEKLY rows.
        short_reset = plan.resets_short_ms // 1000 if plan.resets_short_ms else None
        weekly_reset = plan.resets_weekly_ms // 1000 if plan.resets_weekly_ms else None
        self.five_row.update(
            pct=plan.short_pct,
            sub=f"RESETS · {human_countdown(short_reset).upper()}",
            stale=stale,
            cfg=cfg,
        )
        self.week_row.update(
            pct=plan.weekly_pct,
            sub=f"RESETS · {reset_wall_clock(weekly_reset).upper()}",
            stale=stale,
            cfg=cfg,
        )

        # Extras — build once, then update in place. We dispatch on widget
        # type so popup.py doesn't need to know about provider internals
        # beyond the well-known widget classes.
        if not self._extras_built:
            self._build_extras(plan, cfg, palette)
        for widget in self._extras_widgets:
            self._update_extra(widget, plan, cfg)

        # UPDATED line — for stateful providers only (presence of updated_at).
        updated_at = int((plan.details or {}).get("updated_at") or 0)
        if updated_at:
            suffix = " · IDLE" if stale else ""
            self.updated_label.set_label(
                f"UPDATED {human_ago(updated_at).upper()}{suffix}"
            )
            self.updated_label.set_visible(True)
        else:
            self.updated_label.set_visible(False)

        # Error line.
        if plan.error:
            self.error_label.set_label(f"ERROR: {plan.error.upper()}")
            self.error_label.set_visible(True)
        else:
            self.error_label.set_visible(False)

    def _update_extra(self, widget: Gtk.Widget, plan: PlanStatus, cfg: dict) -> None:
        """Dispatch a widget update based on its type.

        Extras returned by providers are one of the three public row
        classes (TodayRow, SessionRow, McpQuotaRow). Any provider that
        wants a custom widget should either fit one of these shapes or be
        extended here.
        """
        details = plan.details or {}
        if isinstance(widget, TodayRow):
            widget.update(details.get("today") or {})
        elif isinstance(widget, SessionRow):
            widget.update(details.get("session") or {})
        elif isinstance(widget, McpQuotaRow):
            widget.update(details.get("mcp") or {}, cfg=cfg)
        # Unknown widgets: leave them alone — the provider is responsible
        # for managing state via closures if it wants something bespoke.


# ─── Empty-state card ─────────────────────────────────────────────────────


class EmptyCard(Gtk.Box):
    """Single card shown when no providers are enabled in the config."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("cp-card")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        brand = Gtk.Label(xalign=0.0)
        brand.set_use_markup(True)
        brand.set_markup(
            '<span letter_spacing="440">CODING PLANS</span>'
            '  <span foreground="#727272">·</span>  '
            '<span letter_spacing="440">USAGE</span>'
        )
        brand.add_css_class("cp-brand")
        brand.set_hexpand(True)
        header.append(brand)
        self.append(header)

        rule = Gtk.Box()
        rule.add_css_class("cp-rule")
        self.append(rule)

        msg = Gtk.Label(
            label="NO PROVIDERS ENABLED — edit ~/.config/coding-plans/config.toml",
            xalign=0.0,
            wrap=True,
        )
        msg.add_css_class("cp-empty")
        self.append(msg)


# ─── Application ──────────────────────────────────────────────────────────


class UsagePopup(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="dev.coding-plans.popup",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.connect("activate", self.on_activate)
        self.cards: list[ProviderCard] = []

    def on_activate(self, app: Adw.Application) -> None:
        self.cfg = load_config()
        self.palette = load_palette()
        self.providers = load_enabled(self.cfg)

        self.window = Adw.ApplicationWindow(application=app)
        self.window.add_css_class("coding-plans-popup")
        self.window.set_title("Coding Plans Usage")
        self.window.set_default_size(340, 0)
        self.window.set_resizable(False)

        try_layer_shell(self.window)

        # Escape dismisses. No focus-out close — mirror upstream.
        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", self._on_key)
        self.window.add_controller(key)

        provider = Gtk.CssProvider()
        provider.load_from_data(build_css(self.palette).encode())
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Vertical stack: one card per provider, plus a footer at the bottom.
        stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        stack.add_css_class("cp-stack")

        if self.providers:
            for p in self.providers:
                card = ProviderCard(p)
                self.cards.append(card)
                stack.append(card)
        else:
            stack.append(EmptyCard())

        stack.append(self._build_footer())

        self.window.set_content(stack)
        # Present before loading data — instant-feeling UI.
        self.window.present()
        GLib.idle_add(self._first_refresh)
        GLib.timeout_add_seconds(1, self._tick)

    def _first_refresh(self) -> bool:
        self.refresh()
        return False

    def _build_footer(self) -> Gtk.Widget:
        wrap = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        wrap.add_css_class("cp-footer")

        settings_btn = Gtk.Button(label="Settings")
        settings_btn.set_hexpand(True)
        settings_btn.connect("clicked", self._on_settings)

        wrap.append(settings_btn)
        return wrap

    def _tick(self) -> bool:
        self.refresh()
        return True

    def refresh(self) -> None:
        if not self.cards:
            return
        for card in self.cards:
            plan = _safe_fetch(card.provider, self.cfg)
            card.update(plan, self.cfg, self.palette)

    def _shutdown(self) -> None:
        """Force-exit. Adw.Application.quit() and window.close() both leave
        the process alive under gtk4-layer-shell OVERLAY windows, so we
        destroy the window, drop the PID file, and os._exit for certainty.
        """
        try:
            self.window.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            PIDFILE.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        os._exit(0)

    def _on_settings(self, *_args: object) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not CONFIG_PATH.exists():
            CONFIG_PATH.write_text("# edit to taste — see config.toml.example\n")

        term_editors = {"vi", "vim", "nvim", "nano", "emacs", "helix", "hx"}
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or ""
        editor_bin = os.path.basename(editor.split()[0]) if editor else ""

        if editor_bin in term_editors:
            terminal = (
                os.environ.get("TERMINAL")
                or next(
                    (
                        t
                        for t in ("alacritty", "kitty", "ghostty", "foot", "wezterm")
                        if subprocess.run(["which", t], capture_output=True).returncode
                        == 0
                    ),
                    None,
                )
            )
            if terminal:
                cmd = [terminal, "-e", editor_bin, str(CONFIG_PATH)]
            else:
                cmd = ["xdg-open", str(CONFIG_PATH)]
        elif editor:
            cmd = [editor_bin, str(CONFIG_PATH)]
        else:
            cmd = ["xdg-open", str(CONFIG_PATH)]

        try:
            subprocess.Popen(cmd, start_new_session=True)
        except (FileNotFoundError, OSError):
            subprocess.Popen(["xdg-open", str(CONFIG_PATH)], start_new_session=True)
        self._shutdown()

    def _on_key(self, _ctl: Gtk.EventControllerKey, keyval: int, *_rest: object) -> bool:
        from gi.repository import Gdk

        if keyval == Gdk.KEY_Escape:
            self._shutdown()
            return True
        return False


# ─── Entry point ──────────────────────────────────────────────────────────


def main() -> int:
    if toggle_existing():
        return 0
    PIDFILE.write_text(str(os.getpid()))

    def cleanup(*_: object) -> None:
        try:
            PIDFILE.unlink(missing_ok=True)
        finally:
            sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    app = UsagePopup()
    try:
        return app.run(None)
    finally:
        PIDFILE.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
