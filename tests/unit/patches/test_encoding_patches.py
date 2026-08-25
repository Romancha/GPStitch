"""Tests for encoding_patches — force UTF-8 on gopro_overlay I/O (issue #27).

gopro_overlay reads text using the OS locale encoding instead of UTF-8:

- ``process.invoke()`` runs subprocesses with ``text=True`` and no ``encoding``,
  so ffprobe's UTF-8 JSON is decoded with the locale codec. On a Chinese Windows
  (cp936/GBK) a path like ``H:\\新建文件夹\\x.MP4`` turns into mojibake in which
  GBK swallows one backslash of the JSON-escaped ``\\\\`` and leaves the other
  dangling, producing ``json.decoder.JSONDecodeError: Invalid \\escape``.
- ``gpx.load()`` and ``layout_xml.load_xml_layout()`` call ``open()`` without an
  ``encoding``, so a UTF-8 GPX (IGPSPORT/OpenTracks write a BOM) raises
  ``UnicodeDecodeError: 'gbk' codec can't decode byte 0xbf in position 2``.

These are fast contract tests asserting an explicit UTF-8 encoding is used.
The end-to-end reproduction under a real non-UTF-8 locale lives in
tests/integration/test_non_utf8_locale.py.
"""

import gzip
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.fixtures.data import BOM_GPX_BYTES

NON_ASCII_LAYOUT_XML = '<layout>\n  <component type="text" x="0" y="0">速度</component>\n</layout>\n'

UTF8_ALIASES = {"utf-8", "utf8", "utf_8", "utf-8-sig", "utf_8_sig"}


@pytest.fixture(autouse=True)
def _apply_patches():
    """Encoding patches are idempotent and process-wide; apply before each test."""
    from gpstitch.patches.encoding_patches import patch_text_encoding

    patch_text_encoding()


@pytest.fixture
def bom_gpx(tmp_path):
    path = tmp_path / "ride.gpx"
    path.write_bytes(BOM_GPX_BYTES)
    return path


def _assert_utf8(encoding):
    assert encoding is not None, "expected an explicit encoding, got None (falls back to OS locale)"
    assert encoding.lower().replace("_", "-") in {a.replace("_", "-") for a in UTF8_ALIASES}, (
        f"expected a UTF-8 encoding, got {encoding!r}"
    )


class TestFFMPEGInvokeEncoding:
    """FFMPEG.invoke() must decode subprocess output as UTF-8, not the OS locale."""

    def test_invoke_forces_utf8(self):
        from gopro_overlay.ffmpeg import FFMPEG

        invoke_fn = Mock(return_value=Mock(stdout="{}"))
        FFMPEG(invoke_fn=invoke_fn).invoke(["-version"])

        _assert_utf8(invoke_fn.call_args.kwargs.get("encoding"))

    def test_invoke_replaces_undecodable_bytes(self):
        """errors='replace' keeps a stray non-UTF-8 byte from killing the whole call."""
        from gopro_overlay.ffmpeg import FFMPEG

        invoke_fn = Mock(return_value=Mock(stdout="{}"))
        FFMPEG(invoke_fn=invoke_fn).invoke(["-version"])

        assert invoke_fn.call_args.kwargs.get("errors") == "replace"

    def test_invoke_respects_caller_supplied_encoding(self):
        """An explicit caller encoding must win over the patch default."""
        from gopro_overlay.ffmpeg import FFMPEG

        invoke_fn = Mock(return_value=Mock(stdout="{}"))
        FFMPEG(invoke_fn=invoke_fn).invoke(["-version"], encoding="latin-1")

        assert invoke_fn.call_args.kwargs["encoding"] == "latin-1"

    def test_ffprobe_child_also_patched(self):
        """ffprobe() builds a new FFMPEG — the real ffprobe JSON path must be covered too."""
        from gopro_overlay.ffmpeg import FFMPEG

        invoke_fn = Mock(return_value=Mock(stdout="{}"))
        FFMPEG(invoke_fn=invoke_fn).ffprobe().invoke(["-show_streams"])

        _assert_utf8(invoke_fn.call_args.kwargs.get("encoding"))

    def test_run_stays_binary(self):
        """FFMPEG.run() pipes raw video bytes — injecting an encoding would corrupt it."""
        import gopro_overlay.ffmpeg as ffmpeg_module
        from gopro_overlay.ffmpeg import FFMPEG

        captured = {}

        def fake_run(cmd, **kwargs):
            captured.update(kwargs)
            return Mock()

        original_run = ffmpeg_module.run
        ffmpeg_module.run = fake_run
        try:
            FFMPEG().run(["-i", "in.mp4"])
        finally:
            ffmpeg_module.run = original_run

        assert "encoding" not in captured
        assert "errors" not in captured

    def test_patch_is_idempotent(self):
        from gopro_overlay.ffmpeg import FFMPEG

        from gpstitch.patches.encoding_patches import patch_text_encoding

        first = FFMPEG.invoke
        patch_text_encoding()
        patch_text_encoding()

        assert FFMPEG.invoke is first

    def test_invoke_still_passes_args_and_returns_result(self):
        """The patch must not change invoke()'s contract."""
        from gopro_overlay.ffmpeg import FFMPEG

        sentinel = Mock(stdout='{"streams": []}')
        invoke_fn = Mock(return_value=sentinel)

        result = FFMPEG(invoke_fn=invoke_fn).ffprobe().invoke(["-show_streams", "a.mp4"])

        assert result is sentinel
        assert invoke_fn.call_args.args[0] == ["ffprobe", "-show_streams", "a.mp4"]


class TestGpxLoadEncoding:
    """gopro_overlay.gpx.load() must read GPX as UTF-8, not the OS locale."""

    def test_load_uses_explicit_encoding(self, bom_gpx, spy_encoding):
        from gopro_overlay import gpx as gpx_module
        from gopro_overlay.units import units

        seen = spy_encoding(Path, "open")
        gpx_module.load(bom_gpx, units)

        _assert_utf8(seen.get("encoding"))

    def test_load_parses_bom_and_non_ascii_gpx(self, bom_gpx):
        from gopro_overlay import gpx as gpx_module
        from gopro_overlay.units import units

        points = gpx_module.load(bom_gpx, units)

        assert len(points) == 2
        assert points[0].lat == pytest.approx(34.1745849698782)

    def test_load_timeseries_parses_bom_gpx(self, bom_gpx):
        """load_timeseries() is what load_external() actually calls."""
        from gopro_overlay import gpx as gpx_module
        from gopro_overlay.units import units

        ts = gpx_module.load_timeseries(bom_gpx, units)

        assert len(ts.items()) == 2

    def test_load_external_parses_bom_gpx(self, bom_gpx):
        """The full path GPStitch uses for user-supplied GPX files."""
        from gopro_overlay.loading import load_external
        from gopro_overlay.units import units

        ts = load_external(bom_gpx, units)

        assert len(ts.items()) == 2

    def test_gzipped_gpx_still_loads(self, tmp_path):
        """The .gz branch reads bytes and must keep working after the patch."""
        from gopro_overlay import gpx as gpx_module
        from gopro_overlay.units import units

        path = tmp_path / "ride.gpx.gz"
        path.write_bytes(gzip.compress(BOM_GPX_BYTES))

        assert len(gpx_module.load(path, units)) == 2

    def test_patch_is_idempotent(self):
        from gopro_overlay import gpx as gpx_module

        from gpstitch.patches.encoding_patches import patch_text_encoding

        first = gpx_module.load
        patch_text_encoding()

        assert gpx_module.load is first


class TestLayoutXmlEncoding:
    """gopro_overlay.layout_xml.load_xml_layout() must read layouts as UTF-8."""

    def test_load_uses_explicit_encoding(self, tmp_path, spy_encoding):
        from gopro_overlay.layout_xml import load_xml_layout

        path = tmp_path / "custom.xml"
        path.write_text(NON_ASCII_LAYOUT_XML, encoding="utf-8")

        seen = spy_encoding(Path, "open")
        load_xml_layout(path)

        _assert_utf8(seen.get("encoding"))

    def test_load_reads_non_ascii_layout(self, tmp_path):
        from gopro_overlay.layout_xml import load_xml_layout

        path = tmp_path / "custom.xml"
        path.write_text(NON_ASCII_LAYOUT_XML, encoding="utf-8")

        assert "速度" in load_xml_layout(path)

    def test_builtin_layout_still_loads(self):
        """The fallback branch resolves a packaged layout by name."""
        from gopro_overlay.layout_xml import load_xml_layout

        assert "<layout" in load_xml_layout(Path("default-1920x1080"))


class TestConfigEncoding:
    """gopro_overlay.config.Config reads user-defined ffmpeg-profiles.json."""

    NON_ASCII_PROFILES = '{"高质量": {"input": [], "output": ["-c:v", "libx264"]}}'

    def test_maybe_uses_explicit_encoding(self, tmp_path, spy_encoding):
        from gopro_overlay.config import Config

        (tmp_path / "ffmpeg-profiles.json").write_text(self.NON_ASCII_PROFILES, encoding="utf-8")

        seen = spy_encoding(Path, "open")
        Config(tmp_path).maybe("ffmpeg-profiles.json")

        _assert_utf8(seen.get("encoding"))

    def test_maybe_reads_non_ascii_profiles(self, tmp_path):
        from gopro_overlay.config import Config

        (tmp_path / "ffmpeg-profiles.json").write_text(self.NON_ASCII_PROFILES, encoding="utf-8")

        config_file = Config(tmp_path).maybe("ffmpeg-profiles.json")

        assert "高质量" in config_file.content

    def test_missing_file_still_returns_empty_config(self, tmp_path):
        from gopro_overlay.config import Config

        config_file = Config(tmp_path).maybe("ffmpeg-profiles.json")

        assert config_file.content is None


class TestApplyPatches:
    """apply_patches() must wire in the encoding patches like the other ones."""

    def test_apply_patches_applies_encoding_patches(self):
        import gopro_overlay.gpx as gpx_module
        from gopro_overlay.ffmpeg import FFMPEG

        from gpstitch.patches import apply_patches

        apply_patches()

        assert getattr(FFMPEG, "_ts_encoding_patched", False) is True
        assert getattr(gpx_module, "_ts_encoding_patched", False) is True
