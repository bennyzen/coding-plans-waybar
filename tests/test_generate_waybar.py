"""``share/_generate_waybar.py`` — module + style CSS emission."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GEN_PATH = REPO / "share" / "_generate_waybar.py"


def _load():
    spec = importlib.util.spec_from_file_location("_gen_waybar", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules["_gen_waybar"] = mod
    spec.loader.exec_module(mod)
    return mod


def _cfg(style=None, provider_style=None):
    base = {
        "providers": {"zai": {"enabled": True}},
    }
    if style:
        base["style"] = style
    if provider_style:
        base["providers"]["zai"]["style"] = provider_style
    return base


def test_style_single_layer_without_bg_color(tmp_path):
    gen = _load()
    icons = tmp_path / "icons"
    icons.mkdir()
    (icons / "zai.svg").write_text("<svg/>")
    css = gen.generate_style(_cfg(), icons)
    assert "radial-gradient" not in css
    assert 'background-image: url("' in css
    # Single-layer size + position — no comma.
    assert "background-size: 13px 13px;" in css
    assert "background-position: 6px center;" in css


def test_style_emits_disc_when_bg_color_set(tmp_path):
    gen = _load()
    icons = tmp_path / "icons"
    icons.mkdir()
    (icons / "zai.svg").write_text("<svg/>")
    css = gen.generate_style(_cfg(style={"icon_bg_color": "#ffffff"}), icons)
    assert "radial-gradient" not in css
    assert "calc(" not in css  # literal px, not calc().
    disc = icons / "disc-ffffff.svg"
    assert disc.exists()
    assert f'url("{disc}")' in css
    assert "<circle" in disc.read_text()
    # 13px icon + 2px padding each side → 17px disc at 4px X (6 - 2).
    assert "background-size: 13px 13px, 17px 17px;" in css
    assert "background-position: 6px center, 4px center;" in css


def test_style_per_provider_bg_overrides_global(tmp_path):
    gen = _load()
    icons = tmp_path / "icons"
    icons.mkdir()
    (icons / "zai.svg").write_text("<svg/>")
    cfg = _cfg(provider_style={"icon_bg_color": "#eeeeee", "icon_bg_padding": "3px"})
    css = gen.generate_style(cfg, icons)
    disc = icons / "disc-eeeeee.svg"
    assert disc.exists()
    assert f'url("{disc}")' in css
    # 13 + 2*3 = 19.
    assert "background-size: 13px 13px, 19px 19px;" in css
