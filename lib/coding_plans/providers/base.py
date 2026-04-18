"""Provider protocol + PlanStatus dataclass.

A provider fetches usage data for one AI coding-plan subscription and returns
a ``PlanStatus``. The renderer turns ``PlanStatus`` objects into Waybar JSON
(bar label, tooltip, CSS class) and — optionally — GTK4 popup cards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: F401 — used in Provider protocol annotation
from typing import Any, Protocol, runtime_checkable

STATUS_CLASSES = ("fresh", "stale", "critical", "exhausted", "empty")


@dataclass
class PlanStatus:
    """Normalised per-provider usage snapshot."""

    provider_id: str
    display_name: str

    # Short-window (~5h) utilisation, 0–100. ``None`` if the provider doesn't
    # expose a short window or data is missing.
    short_pct: int | None = None
    # Long-window (weekly / 7d) utilisation, 0–100.
    weekly_pct: int | None = None
    # Epoch milliseconds of the next reset for each window.
    resets_short_ms: int | None = None
    resets_weekly_ms: int | None = None

    plan_tier: str | None = None
    status_class: str = "empty"

    # ``(label, value)`` pairs rendered in the tooltip / popup after the
    # standard rows. Used for provider-specific fields (MCP quota, today's
    # tokens, session context, …).
    extra_rows: list[tuple[str, str]] = field(default_factory=list)

    # Raw provider-specific payload. Popup cards may introspect this when they
    # need richer layout than ``extra_rows`` permits.
    details: dict[str, Any] = field(default_factory=dict)

    error: str | None = None

    def __post_init__(self) -> None:
        if self.status_class not in STATUS_CLASSES:
            raise ValueError(f"invalid status_class: {self.status_class!r}")


@runtime_checkable
class Provider(Protocol):
    """What every provider module's ``PROVIDER`` object must satisfy."""

    id: str
    display_name: str
    # Path to the provider's brand SVG (co-located at providers/icons/<id>.svg).
    # The bar label uses ``display_name`` (Pango in Waybar can't inline SVGs);
    # the popup renders the SVG directly. Optional: None means no brand icon.
    icon_path: "Path | None"
    # Pango foreground hex when the SVG should be tinted (e.g. Claude's
    # brand orange). None = render with the active theme's text colour.
    icon_color: str | None

    def fetch(self, config: dict[str, Any]) -> PlanStatus:
        """Return a ``PlanStatus`` for the current moment. MUST NOT raise —
        failures return a ``PlanStatus`` with ``error`` set and
        ``status_class='stale'``."""
        ...
