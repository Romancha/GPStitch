"""End-to-end reproduction of issue #27 under a real non-UTF-8 locale.

The reported failures only happen when Python's locale encoding is not UTF-8
(the reporter runs a Chinese Windows, cp936/GBK). A UTF-8 host cannot be made to
behave like GBK by monkeypatching — ``open()`` resolves its default encoding at
the C level. So these tests re-run the failing code in a child interpreter with
``LC_ALL=C`` and UTF-8 mode disabled, which gives an ASCII locale encoding.

ASCII and GBK fail on different bytes but through the same mechanism: text that
gopro_overlay reads with the locale codec instead of UTF-8. Both surface as the
tracebacks in the issue:

    UnicodeDecodeError: 'gbk' codec can't decode byte 0xbf in position 2
    json.decoder.JSONDecodeError: Invalid \\escape: line 120 column 34

Skipped on Windows, where the locale encoding is chosen by the system code page
rather than by these environment variables.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.data import BOM_GPX_BYTES

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="LC_ALL does not drive the locale encoding on Windows"),
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _path_expr(path: Path) -> str:
    """A Python expression for `path` that survives the child's ASCII locale.

    On Linux an ASCII locale also makes the filesystem encoding ASCII, so a str
    path with non-ASCII characters cannot be passed to open() or a subprocess
    there. Decoding the raw bytes in the child yields a surrogate-escaped str that
    encodes back to the same bytes (on macOS the filesystem encoding is always
    UTF-8, so it is a plain str).
    """
    return f"os.fsdecode({os.fsencode(path)!r})"


def _run_in_ascii_locale(code: str, apply_patches: bool = True):
    """Run `code` in a child interpreter whose locale encoding is ASCII."""
    # On Linux the child decodes its own command line with the ASCII locale codec,
    # so non-ASCII source text never compiles there. Use _path_expr() for paths and
    # ascii() escapes for literals.
    assert code.isascii(), "child code must be ASCII; see _path_expr()"

    env = {k: v for k, v in os.environ.items() if k not in ("LANG", "LC_CTYPE", "LC_ALL")}
    env.update(
        {
            "LC_ALL": "C",
            "PYTHONUTF8": "0",
            "PYTHONCOERCECLOCALE": "0",
            "PYTHONIOENCODING": "utf-8",  # so the child can print its result back to us
        }
    )

    preamble = "from gpstitch.patches import apply_patches; apply_patches()\n" if apply_patches else ""
    guard = (
        "import locale, sys\n"
        "assert locale.getencoding().lower().replace('-', '_') in ('ascii', 'us_ascii', 'ansi_x3.4_1968'), (\n"
        "    'child locale is not ASCII: ' + locale.getencoding())\n"
        "assert sys.flags.utf8_mode == 0, 'child is in UTF-8 mode'\n"
        "import os\n"
    )

    return subprocess.run(
        [sys.executable, "-c", guard + preamble + code],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


@pytest.fixture(scope="module")
def ascii_locale_available():
    """Confirm the child interpreter really gets a non-UTF-8 locale on this host."""
    result = _run_in_ascii_locale("print('OK')", apply_patches=False)
    if result.returncode != 0:
        pytest.skip(f"cannot obtain a non-UTF-8 locale here: {result.stderr.strip()[:300]}")
    return True


class TestGpxUnderNonUtf8Locale:
    """Reproduces: UnicodeDecodeError: 'gbk' codec can't decode byte 0xbf in position 2."""

    @pytest.fixture
    def gpx_path(self, tmp_path):
        path = tmp_path / "ride-0-2026-08-19-15-00-26.gpx"
        path.write_bytes(BOM_GPX_BYTES)
        return path

    def test_unpatched_library_fails(self, gpx_path, ascii_locale_available):
        """Guards the premise: without the patch this really is broken."""
        result = _run_in_ascii_locale(
            f"from pathlib import Path\n"
            f"from gopro_overlay.loading import load_external\n"
            f"from gopro_overlay.units import units\n"
            f"load_external(Path({_path_expr(gpx_path)}), units)\n",
            apply_patches=False,
        )

        assert result.returncode != 0, "expected the unpatched library to fail on a BOM'd UTF-8 GPX"
        assert "UnicodeDecodeError" in result.stderr

    def test_patched_load_external_succeeds(self, gpx_path, ascii_locale_available):
        result = _run_in_ascii_locale(
            f"from pathlib import Path\n"
            f"from gopro_overlay.loading import load_external\n"
            f"from gopro_overlay.units import units\n"
            f"ts = load_external(Path({_path_expr(gpx_path)}), units)\n"
            f"print('POINTS', len(ts.items()))\n"
        )

        assert result.returncode == 0, result.stderr
        assert "POINTS 2" in result.stdout


class TestFfprobeUnderNonUtf8Locale:
    """Reproduces: json.decoder.JSONDecodeError: Invalid \\escape (non-ASCII path)."""

    @pytest.fixture
    def video_in_non_ascii_dir(self, tmp_path, integration_test_video):
        """The reporter's path was H:\\新建文件夹\\20260802141505_000133.MP4."""
        import shutil

        directory = tmp_path / "新建文件夹"
        directory.mkdir()
        target = directory / integration_test_video.name
        shutil.copy(integration_test_video, target)
        return target

    def test_unpatched_library_fails(self, video_in_non_ascii_dir, ascii_locale_available):
        """Guards the premise: ffprobe's UTF-8 JSON is undecodable under an ASCII locale."""
        result = _run_in_ascii_locale(
            f"from pathlib import Path\n"
            f"from gopro_overlay.ffmpeg import FFMPEG\n"
            f"from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro\n"
            f"FFMPEGGoPro(FFMPEG()).find_recording(Path({_path_expr(video_in_non_ascii_dir)}))\n",
            apply_patches=False,
        )

        assert result.returncode != 0, "expected the unpatched library to fail on a non-ASCII video path"
        assert "UnicodeDecodeError" in result.stderr or "JSONDecodeError" in result.stderr

    def test_patched_find_recording_succeeds(self, video_in_non_ascii_dir, ascii_locale_available):
        result = _run_in_ascii_locale(
            f"from pathlib import Path\n"
            f"from gopro_overlay.ffmpeg import FFMPEG\n"
            f"from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro\n"
            f"r = FFMPEGGoPro(FFMPEG()).find_recording(Path({_path_expr(video_in_non_ascii_dir)}))\n"
            f"print('DIMENSION', r.video.dimension.x, r.video.dimension.y)\n"
        )

        assert result.returncode == 0, result.stderr
        assert "DIMENSION" in result.stdout

    def test_unpatched_ffprobe_json_is_undecodable(self, video_in_non_ascii_dir, ascii_locale_available):
        """The reporter's exact crash: ffprobe's JSON carries the non-ASCII path.

        `-show_format` puts the file path in a JSON "filename" field. Decoding that
        with a non-UTF-8 locale codec is what produced `Invalid \\escape` on GBK.
        """
        result = _run_in_ascii_locale(
            f"import json\n"
            f"from gopro_overlay.ffmpeg import FFMPEG\n"
            f"out = FFMPEG().ffprobe().invoke(\n"
            f"    ['-hide_banner', '-print_format', 'json', '-show_format', {_path_expr(video_in_non_ascii_dir)}]\n"
            f").stdout\n"
            f"json.loads(str(out))\n",
            apply_patches=False,
        )

        assert result.returncode != 0, "expected ffprobe JSON to be undecodable under a non-UTF-8 locale"
        assert "UnicodeDecodeError" in result.stderr or "JSONDecodeError" in result.stderr

    def test_patched_ffprobe_json_round_trips_the_path(self, video_in_non_ascii_dir, ascii_locale_available):
        result = _run_in_ascii_locale(
            f"import json\n"
            f"from gopro_overlay.ffmpeg import FFMPEG\n"
            f"out = FFMPEG().ffprobe().invoke(\n"
            f"    ['-hide_banner', '-print_format', 'json', '-show_format', {_path_expr(video_in_non_ascii_dir)}]\n"
            f").stdout\n"
            f"data = json.loads(str(out))\n"
            f"print('FILENAME_OK', {'新建文件夹'!a} in data['format']['filename'])\n"
        )

        assert result.returncode == 0, result.stderr
        assert "FILENAME_OK True" in result.stdout

    def test_patched_gpstitch_creation_time_succeeds(self, video_in_non_ascii_dir, ascii_locale_available):
        """GPStitch's own ffprobe caller — same invoke(), same -show_format JSON."""
        result = _run_in_ascii_locale(
            f"from pathlib import Path\n"
            f"from gpstitch.services.renderer import _extract_creation_time\n"
            f"dt = _extract_creation_time(Path({_path_expr(video_in_non_ascii_dir)}))\n"
            f"assert dt is not None, 'creation_time extraction returned None'\n"
            f"print('CREATION_TIME', dt.isoformat())\n"
        )

        assert result.returncode == 0, result.stderr
        assert "CREATION_TIME 2024-08-06" in result.stdout


class TestLayoutXmlUnderNonUtf8Locale:
    """A custom template with non-ASCII labels must load under any locale."""

    @pytest.fixture
    def layout_path(self, tmp_path):
        path = tmp_path / "custom.xml"
        path.write_text(
            '<layout>\n  <component type="text" x="0" y="0">速度</component>\n</layout>\n', encoding="utf-8"
        )
        return path

    def test_unpatched_library_fails(self, layout_path, ascii_locale_available):
        result = _run_in_ascii_locale(
            f"from pathlib import Path\n"
            f"from gopro_overlay.layout_xml import load_xml_layout\n"
            f"load_xml_layout(Path({_path_expr(layout_path)}))\n",
            apply_patches=False,
        )

        assert result.returncode != 0, "expected the unpatched library to fail on a non-ASCII layout"
        assert "UnicodeDecodeError" in result.stderr

    def test_patched_load_xml_layout_succeeds(self, layout_path, ascii_locale_available):
        result = _run_in_ascii_locale(
            f"from pathlib import Path\n"
            f"from gopro_overlay.layout_xml import load_xml_layout\n"
            f"xml = load_xml_layout(Path({_path_expr(layout_path)}))\n"
            f"print('LOADED', {'速度'!a} in xml)\n"
        )

        assert result.returncode == 0, result.stderr
        assert "LOADED True" in result.stdout


class TestRenderSubprocessUtf8Mode:
    """PYTHONUTF8=1 must make the render child immune regardless of the host locale."""

    def test_utf8_mode_env_neutralises_ascii_locale(self, tmp_path, ascii_locale_available):
        gpx_path = tmp_path / "ride.gpx"
        gpx_path.write_bytes(BOM_GPX_BYTES)

        env = {k: v for k, v in os.environ.items() if k not in ("LANG", "LC_CTYPE", "LC_ALL")}
        env.update({"LC_ALL": "C", "PYTHONCOERCECLOCALE": "0", "PYTHONIOENCODING": "utf-8"})

        from gpstitch.services.render_service import render_service

        env.update({k: v for k, v in render_service._get_process_env().items() if k.startswith("PYTHON")})

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path\n"
                "from gopro_overlay.loading import load_external\n"
                "from gopro_overlay.units import units\n"
                f"ts = load_external(Path(r'{gpx_path}'), units)\n"
                "print('POINTS', len(ts.items()))\n",
            ],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

        assert result.returncode == 0, result.stderr
        assert "POINTS 2" in result.stdout
