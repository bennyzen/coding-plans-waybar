"""Waybar custom-module entry point — stub until Claude + Z.AI providers land."""

from __future__ import annotations

import json


def main() -> int:
    print(json.dumps({
        "text": "coding-plans: not yet implemented",
        "tooltip": "scaffold only — see PLAN.md step 3+",
        "class": "empty",
    }))
    return 0
