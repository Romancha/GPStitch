"""Tests for UTF-8 handling in GPStitch's own file and subprocess I/O (issue #27).

Independently of the gopro_overlay bugs, GPStitch reads several text files with
``read_text()``/``open()`` and no ``encoding``, which falls back to the OS locale
codec. On a Chinese Windows (cp936/GBK) a layout XML containing non-ASCII labels
or a UTF-8 BOM raises UnicodeDecodeError instead of loading.

The render subprocess is a second process running the same gopro_overlay code,
so it needs UTF-8 mode in its environment too — patching in-process only fixes
preview, not render.
"""

from pathlib import Path

import pytest

NON_ASCII_LAYOUT_XML = '<layout>\n  <component type="text" x="0" y="0">速度</component>\n</layout>\n'

CAIRO_LAYOUT_XML = '<layout>\n  <component type="cairo_gauge_marker" x="0" y="0">速度</component>\n</layout>\n'


class TestLayoutRequiresCairo:
    """renderer._layout_requires_cairo() reads layout XML from disk."""

    def test_reads_non_ascii_local_layout(self, tmp_path, monkeypatch):
        from gpstitch.services import renderer

        layouts_dir = tmp_path / "layouts"
        layouts_dir.mkdir()
        (layouts_dir / "custom.xml").write_text(CAIRO_LAYOUT_XML, encoding="utf-8")

        monkeypatch.setattr(renderer, "__file__", str(tmp_path / "services" / "renderer.py"))

        assert renderer._layout_requires_cairo("custom") is True

    def test_uses_explicit_encoding(self, tmp_path, monkeypatch, spy_encoding):
        from gpstitch.services import renderer

        layouts_dir = tmp_path / "layouts"
        layouts_dir.mkdir()
        (layouts_dir / "custom.xml").write_text(NON_ASCII_LAYOUT_XML, encoding="utf-8")

        monkeypatch.setattr(renderer, "__file__", str(tmp_path / "services" / "renderer.py"))

        seen = spy_encoding(Path, "read_text")
        renderer._layout_requires_cairo("custom")

        assert seen.get("encoding") is not None, "read_text() without encoding falls back to the OS locale"
        assert seen["encoding"].lower().replace("_", "-").startswith("utf-8")


class TestEditorLayoutRead:
    """api.editor._load_predefined_layout() reads packaged gopro-overlay layout XML."""

    def test_builtin_layout_read_uses_explicit_encoding(self, spy_encoding):
        import builtins

        from gpstitch.api.editor import _load_predefined_layout

        seen = spy_encoding(builtins, "open", match=".xml")
        _load_predefined_layout("default-1920x1080")

        assert seen.get("encoding") is not None, "open() without encoding falls back to the OS locale"
        assert seen["encoding"].lower().replace("_", "-").startswith("utf-8")


class TestRenderSubprocessEnv:
    """The render subprocess must run in UTF-8 mode."""

    def test_env_enables_utf8_mode(self):
        from gpstitch.services.render_service import render_service

        env = render_service._get_process_env()

        assert env.get("PYTHONUTF8") == "1"

    def test_env_sets_io_encoding(self):
        """Progress lines are decoded as UTF-8 by the parent — the child must emit UTF-8."""
        from gpstitch.services.render_service import render_service

        env = render_service._get_process_env()

        assert env.get("PYTHONIOENCODING", "").lower().startswith("utf-8")

    def test_env_keeps_existing_settings(self):
        from gpstitch.services.render_service import render_service

        env = render_service._get_process_env()

        assert env.get("PYTHONUNBUFFERED") == "1"
        assert "PYTHONPATH" in env


def _locale_dependent_text_io(source: str) -> list[str]:
    """Return `file:line` for text I/O calls that would fall back to the OS locale.

    Binary modes carry no encoding, so `open(p, "rb")` and friends are exempt.
    """
    import ast

    offenders = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if isinstance(func, ast.Attribute):
            # Attribute calls: only Path-style text helpers. A bare `.open()` is
            # ambiguous (MapRenderer.open(style) is not file I/O), so skip it.
            name = func.attr
            if name not in ("read_text", "write_text"):
                continue
        elif isinstance(func, ast.Name) and func.id == "open":
            name = "open"
        else:
            continue

        if any(kw.arg == "encoding" for kw in node.keywords):
            continue

        mode = next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
        if mode is None and name == "open" and len(node.args) > 1:
            mode = node.args[1]
        if isinstance(mode, ast.Constant) and "b" in str(mode.value):
            continue

        offenders.append(f"{name}() at line {node.lineno}")

    return offenders


@pytest.mark.parametrize(
    "module_name",
    [
        "gpstitch.services.renderer",
        "gpstitch.services.render_service",
        "gpstitch.services.file_manager",
        "gpstitch.services.template_service",
        "gpstitch.services.job_manager",
        "gpstitch.api.editor",
        "gpstitch.patches.encoding_patches",
    ],
)
def test_no_locale_dependent_text_io(module_name):
    """Guard against reintroducing encoding-less text I/O in the modules we fixed."""
    import importlib

    module = importlib.import_module(module_name)
    source = Path(module.__file__).read_text(encoding="utf-8")

    offenders = _locale_dependent_text_io(source)

    assert not offenders, f"{module_name} has locale-dependent text I/O: {offenders}"
