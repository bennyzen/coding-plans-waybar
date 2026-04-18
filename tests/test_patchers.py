"""Installer patcher scripts — idempotency + marker-guarded edits."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATCH_WAYBAR = REPO / "share/_patch_waybar.py"
PATCH_STYLE = REPO / "share/_patch_style.py"
PATCH_TOML = REPO / "share/_patch_toml.py"


def _run(cmd, env=None):
    result = subprocess.run(
        cmd, check=True, capture_output=True, text=True, env=env,
    )
    return result


def test_waybar_install_idempotent(tmp_path):
    cfg = tmp_path / "config.jsonc"
    module = tmp_path / "module.jsonc"
    cfg.write_text('{\n  "modules-right": []\n}\n')
    module.write_text('"custom/coding-plans": { "exec": "coding-plans-bar" }\n')

    _run([sys.executable, str(PATCH_WAYBAR), "install", str(cfg), str(module)])
    first = cfg.read_text()
    assert first.count("custom/coding-plans") >= 2  # modules-right + block
    assert first.count("coding-plans-waybar >>>") == 1  # single opening marker

    # Run again — should not duplicate.
    _run([sys.executable, str(PATCH_WAYBAR), "install", str(cfg), str(module)])
    second = cfg.read_text()
    assert second.count("coding-plans-waybar >>>") == 1


def test_waybar_uninstall_removes_block(tmp_path):
    cfg = tmp_path / "config.jsonc"
    module = tmp_path / "module.jsonc"
    cfg.write_text('{\n  "modules-right": []\n}\n')
    module.write_text('"custom/coding-plans": { "exec": "coding-plans-bar" }\n')
    _run([sys.executable, str(PATCH_WAYBAR), "install", str(cfg), str(module)])
    _run([sys.executable, str(PATCH_WAYBAR), "uninstall", str(cfg)])

    final = cfg.read_text()
    assert "custom/coding-plans" not in final
    assert "coding-plans-waybar" not in final


def test_waybar_insert_after_anchor(tmp_path):
    cfg = tmp_path / "config.jsonc"
    module = tmp_path / "module.jsonc"
    cfg.write_text('{\n  "modules-right": ["custom/exit", "clock"]\n}\n')
    module.write_text('"custom/coding-plans": {}\n')

    env = {**__import__("os").environ, "CODING_PLANS_INSERT_AFTER": "custom/exit"}
    _run([sys.executable, str(PATCH_WAYBAR), "install", str(cfg), str(module)], env=env)
    text = cfg.read_text()
    # Find modules-right and ensure order is exit → coding-plans → clock.
    assert text.index("custom/exit") < text.index("custom/coding-plans") < text.index("clock")


def test_style_install_idempotent(tmp_path):
    style = tmp_path / "style.css"
    snippet = tmp_path / "snippet.css"
    style.write_text("#root { color: red; }\n")
    snippet.write_text("#custom-coding-plans { color: green; }\n")

    _run([sys.executable, str(PATCH_STYLE), "install", str(style), str(snippet)])
    first = style.read_text()
    assert first.count(">>> coding-plans-waybar >>>") == 1

    _run([sys.executable, str(PATCH_STYLE), "install", str(style), str(snippet)])
    second = style.read_text()
    assert second.count(">>> coding-plans-waybar >>>") == 1


def test_toml_set_get_chained(tmp_path):
    cfg_dir = tmp_path / "coding-plans"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        '[providers.claude]\nenabled = true\nchained_command = ""\n'
    )
    env = {
        **__import__("os").environ,
        "CFG_DIR_EXPORT": str(cfg_dir),
        "EXISTING_STATUSLINE": 'echo "hello \\"world\\""',
    }
    _run([sys.executable, str(PATCH_TOML), "set-chained"], env=env)

    del env["EXISTING_STATUSLINE"]
    got = _run([sys.executable, str(PATCH_TOML), "get-chained"], env=env).stdout
    assert got == 'echo "hello \\"world\\""'
