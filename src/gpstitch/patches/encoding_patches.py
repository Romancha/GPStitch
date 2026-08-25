"""Force UTF-8 on gopro_overlay text I/O instead of the OS locale encoding.

gopro_overlay reads text without specifying an encoding, so Python falls back to
the locale codec. That is UTF-8 on most systems but not on a Chinese Windows
(cp936/GBK), where two things break (issue #27):

``process.invoke()`` runs subprocesses with ``text=True`` and no ``encoding``,
so ffprobe's UTF-8 JSON is decoded with the locale codec. For a path such as
``H:\\新建文件夹\\x.MP4`` the JSON contains an escaped ``\\\\``; under GBK the
trailing byte of ``夹`` (0xB9) pairs with the first backslash (0x5C is a valid
GBK trail byte) and swallows it, leaving the second backslash dangling::

    json.decoder.JSONDecodeError: Invalid \\escape: line 120 column 34

``gpx.load()`` and ``layout_xml.load_xml_layout()`` call ``open()`` without an
encoding. IGPSPORT and OpenTracks write GPX as UTF-8 with a BOM, whose third
byte is rejected by GBK::

    UnicodeDecodeError: 'gbk' codec can't decode byte 0xbf in position 2

Both are upstream bugs, but they also hit GPStitch's own ffprobe callers
(services/metadata.py, services/renderer.py, services/dji_meta_parser.py), which
share the same ``invoke()``. Patching here fixes every caller at once, in both
the web server and the render subprocess (the wrapper script applies patches
too).

Text reads use ``utf-8-sig`` so a BOM is stripped rather than passed into the XML
parser, and ``errors="replace"`` so a stray non-UTF-8 byte degrades a cosmetic
string instead of failing the whole load — GPS coordinates, timestamps and XML
markup are ASCII and survive intact.
"""

import gzip
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TEXT_ENCODING = "utf-8-sig"
TEXT_ERRORS = "replace"


def patch_text_encoding() -> None:
    """Apply all UTF-8 encoding patches to gopro_overlay. Idempotent."""
    _patch_ffmpeg_invoke()
    _patch_gpx_load()
    _patch_layout_xml_load()
    _patch_config_load()


def _patch_ffmpeg_invoke() -> None:
    """Decode ffmpeg/ffprobe output as UTF-8 rather than the locale encoding.

    Only ``invoke()`` is patched. ``FFMPEG.run()`` pipes raw video bytes and must
    stay binary, and ``stream()`` already uses a binary ``Popen``.

    Patching ``gopro_overlay.process.invoke`` would not work: ``FFMPEG.__init__``
    binds it as the ``invoke_fn`` default argument, which is evaluated once at
    class-definition time, so replacing the module attribute has no effect on
    instances created later.
    """
    from gopro_overlay.ffmpeg import FFMPEG

    if getattr(FFMPEG, "_ts_encoding_patched", False):
        logger.debug("FFMPEG.invoke already patched for encoding, skipping")
        return

    _original = FFMPEG.invoke

    def invoke_utf8(self, args, **kwargs):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", TEXT_ERRORS)
        return _original(self, args, **kwargs)

    FFMPEG.invoke = invoke_utf8
    FFMPEG._ts_encoding_patched = True
    logger.debug("Patched FFMPEG.invoke to decode subprocess output as UTF-8")


def _patch_gpx_load() -> None:
    """Read GPX files as UTF-8 with BOM stripping."""
    import gopro_overlay.gpx as gpx_module

    if getattr(gpx_module, "_ts_encoding_patched", False):
        logger.debug("gpx.load already patched for encoding, skipping")
        return

    def load_utf8(filepath: Path, units):
        if filepath.suffix == ".gz":
            with gzip.open(filepath, "rt", encoding=TEXT_ENCODING, errors=TEXT_ERRORS) as gpx_file:
                return gpx_module.load_xml(gpx_file, units)

        with filepath.open("r", encoding=TEXT_ENCODING, errors=TEXT_ERRORS) as gpx_file:
            return gpx_module.load_xml(gpx_file, units)

    gpx_module.load = load_utf8
    gpx_module._ts_encoding_patched = True
    logger.debug("Patched gopro_overlay.gpx.load to read GPX as UTF-8")


def _patch_layout_xml_load() -> None:
    """Read layout XML (custom templates included) as UTF-8."""
    from importlib.resources import as_file, files

    from gopro_overlay import layout_xml, layouts

    if getattr(layout_xml, "_ts_encoding_patched", False):
        logger.debug("load_xml_layout already patched for encoding, skipping")
        return

    def load_xml_layout_utf8(filepath: Path):
        if filepath.exists():
            with filepath.open("r", encoding=TEXT_ENCODING, errors=TEXT_ERRORS) as f:
                return f.read()

        with as_file(files(layouts) / f"{filepath.name}.xml") as fn:
            return fn.read_text(encoding=TEXT_ENCODING, errors=TEXT_ERRORS)

    layout_xml.load_xml_layout = load_xml_layout_utf8
    layout_xml._ts_encoding_patched = True
    logger.debug("Patched gopro_overlay.layout_xml.load_xml_layout to read layouts as UTF-8")


def _patch_config_load() -> None:
    """Read gopro-overlay config files as UTF-8.

    GPStitch loads user-defined FFmpeg profiles through this
    (``renderer._load_user_ffmpeg_profiles``), and a profile name or comment in
    a non-ASCII script would otherwise be swallowed by the caller's except.
    """
    import json

    from gopro_overlay.config import Config, ConfigFile

    if getattr(Config, "_ts_encoding_patched", False):
        logger.debug("Config.maybe already patched for encoding, skipping")
        return

    def maybe_utf8(self, name: str) -> ConfigFile:
        p = self.location / name
        if p.exists():
            with p.open("r", encoding=TEXT_ENCODING, errors=TEXT_ERRORS) as pf:
                return ConfigFile(content=json.load(pf), location=p)
        return ConfigFile(content=None, location=p)

    Config.maybe = maybe_utf8
    Config._ts_encoding_patched = True
    logger.debug("Patched gopro_overlay.config.Config.maybe to read config as UTF-8")
