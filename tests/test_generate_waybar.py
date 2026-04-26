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


def test_module_uses_absolute_bin_paths():
    """Waybar inherits PATH from its launcher, which often lacks ~/.local/bin.
    Both exec and on-click must spell out the bin dir or the modules silently
    fail to render."""
    gen = _load()
    cfg = {"providers": {"claude": {"enabled": True}, "zai": {"enabled": True}}}
    out = gen.generate_modules(cfg, preload="", bin_dir="/opt/cp/bin")
    assert '"exec": "/opt/cp/bin/coding-plans-bar --provider claude"' in out
    assert '"exec": "/opt/cp/bin/coding-plans-bar --provider zai"' in out
    assert "/opt/cp/bin/coding-plans-popup" in out
    # No bare invocations left over.
    assert '"exec": "coding-plans-bar' not in out
    assert " coding-plans-popup" not in out  # space before = bare invocation


def test_module_strips_trailing_slash_on_bin_dir():
    gen = _load()
    cfg = {"providers": {"zai": {"enabled": True}}}
    out = gen.generate_modules(cfg, preload="", bin_dir="/opt/cp/bin/")
    assert "/opt/cp/bin/coding-plans-bar" in out
    assert "/opt/cp/bin//coding-plans-bar" not in out


def test_module_cli_rejects_missing_bin_dir(tmp_path, capsys, monkeypatch):
    """The 'module' subcommand must refuse to emit unqualified commands."""
    gen = _load()
    monkeypatch.setenv("CFG_DIR_EXPORT", str(tmp_path))
    (tmp_path / "config.toml").write_text('[providers.zai]\nenabled = true\n')
    icons = tmp_path / "icons"
    icons.mkdir()
    import pytest
    with pytest.raises(SystemExit) as exc:
        gen.main(["module", "--icons-dir", str(icons)])
    assert exc.value.code != 0
    assert "--bin-dir" in capsys.readouterr().err
