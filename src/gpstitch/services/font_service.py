"""System font discovery for the overlay font picker."""

import hashlib
import io
import logging
import os
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gpstitch.models.schemas import FontOption

logger = logging.getLogger(__name__)

_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}

# Upper bound on faces read from one collection file (real .ttc files hold a few dozen)
_MAX_FACES_PER_FILE = 256

# Font picker preview: rendered at 2x for HiDPI screens, in the UI's primary text color.
PREVIEW_FONT_SIZE = 32
PREVIEW_MAX_WIDTH = 640
PREVIEW_HEIGHT = 44
PREVIEW_BASELINE = 33
PREVIEW_COLOR = (226, 232, 240, 255)

# Characters every overlay font must have: digits and Latin letters for values and units
_OVERLAY_SAMPLE_CHARS = "0158AKmh"

# Weight rank of style words, lightest to heaviest; synonyms share a rank.
_WEIGHT_RANK = {
    "thin": 0,
    "hairline": 0,
    "extralight": 1,
    "ultralight": 1,
    "light": 2,
    "book": 3,
    "regular": 3,
    "normal": 3,
    "roman": 3,
    "plain": 3,
    "medium": 4,
    "semibold": 5,
    "demibold": 5,
    "bold": 6,
    "extrabold": 7,
    "ultrabold": 7,
    "heavy": 8,
    "black": 8,
}


def _system_font_dirs() -> list[Path]:
    """Directories where the OS (and PIL's font lookup) keeps installed fonts."""
    home = Path.home()
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        dirs = [windir / "Fonts"]
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            dirs.append(Path(local_appdata) / "Microsoft" / "Windows" / "Fonts")
        return dirs
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library" / "Fonts"]
    return [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".local" / "share" / "fonts",
        home / ".fonts",
    ]


def _font_id(path: str, index: int) -> str:
    return hashlib.sha1(f"{path}#{index}".encode()).hexdigest()[:16]


def _style_sort_key(style: str) -> tuple[int, int, str]:
    normalized = style.lower().replace(" ", "").replace("-", "")
    italic = "italic" in normalized or "oblique" in normalized
    weight = normalized.replace("italic", "").replace("oblique", "")
    return _WEIGHT_RANK.get(weight, _WEIGHT_RANK["regular"]), int(italic), style


def _glyph_pixels(pil_font: ImageFont.FreeTypeFont, char: str) -> tuple[tuple[int, int, int, int], bytes]:
    left, top, right, bottom = pil_font.getbbox(char)
    image = Image.new("L", (max(1, right - left), max(1, bottom - top)))
    ImageDraw.Draw(image).text((-left, -top), char, font=pil_font, fill=255)
    return (left, top, right, bottom), image.tobytes()


def _renders_overlay_text(pil_font: ImageFont.FreeTypeFont) -> bool:
    """Whether the face can draw overlay text: digits and basic Latin letters.

    Rules out faces with no Latin glyphs (Arabic-, CJK-only fonts would show boxes for
    every number and unit) and faces FreeType fails on for any text (e.g. macOS Courier
    Oblique: "stack overflow"), which would crash gopro-dashboard.
    """
    try:
        # A missing glyph renders as .notdef, same as a codepoint no font has
        notdef = _glyph_pixels(pil_font, "\U0010fffd")
        return all(_glyph_pixels(pil_font, char) != notdef for char in _OVERLAY_SAMPLE_CHARS)
    except Exception:
        return False


class FontService:
    """Lists installed fonts.

    Reading a font's family/style name means opening the file, which takes ~1ms per font
    and adds up to most of a second on a typical system. Names are cached per file keyed
    by mtime, so each listing only re-walks the directories (a few ms) and parses fonts
    that were added or changed since — newly installed fonts show up without a restart.
    """

    def __init__(self, font_dirs: list[Path] | None = None):
        self._font_dirs = font_dirs
        self._faces_cache: dict[str, tuple[float, list[tuple[int, str, str]]]] = {}
        self._fonts_by_id: dict[str, FontOption] = {}
        self._lock = threading.Lock()

    def _iter_font_files(self) -> Iterator[tuple[str, float]]:
        """Yield (path, mtime) of every font file in the font directories."""
        font_dirs = _system_font_dirs() if self._font_dirs is None else self._font_dirs
        for font_dir in font_dirs:
            for root, _dirs, names in os.walk(font_dir):  # A missing directory yields nothing
                for name in names:
                    if Path(name).suffix.lower() not in _FONT_EXTENSIONS:
                        continue
                    path = os.path.join(root, name)
                    try:
                        yield path, os.stat(path).st_mtime
                    except OSError:
                        continue

    def _read_faces(self, path: str) -> list[tuple[int, str, str]]:
        """Read (index, family, style) of every face in the file that can render text."""
        faces = []
        for index in range(_MAX_FACES_PER_FILE):
            try:
                pil_font = ImageFont.truetype(path, size=12, index=index)
            except Exception as e:
                if index == 0:
                    logger.debug("Skipping unreadable font %s: %s", path, e)
                break  # Past the last face of a collection (or a single-face file)
            family, style = pil_font.getname()
            if not family:
                continue
            if _renders_overlay_text(pil_font):
                faces.append((index, family, style or "Regular"))
            else:
                logger.debug("Skipping font face %s#%d that can't render overlay text", path, index)
        return faces

    def list_fonts(self) -> list[FontOption]:
        """List installed font faces sorted by family, then weight.

        Every face of a .ttc collection is listed with its index. Hidden system faces
        (macOS names starting with '.') are skipped. Duplicate family/style pairs keep
        the first directory's copy.
        """
        with self._lock:
            faces_cache = {}
            for path, mtime in self._iter_font_files():
                cached = self._faces_cache.get(path)
                if cached is not None and cached[0] == mtime:
                    faces_cache[path] = cached
                else:
                    faces_cache[path] = (mtime, self._read_faces(path))
            self._faces_cache = faces_cache

            fonts = []
            seen = set()
            for path, (_mtime, faces) in faces_cache.items():
                for index, family, style in faces:
                    if family.startswith(".") or (family, style) in seen:
                        continue
                    seen.add((family, style))
                    fonts.append(
                        FontOption(id=_font_id(path, index), path=path, index=index, family=family, style=style)
                    )

            fonts.sort(key=lambda f: (f.family.casefold(), _style_sort_key(f.style)))
            self._fonts_by_id = {f.id: f for f in fonts}
            return fonts

    def get_font(self, font_id: str) -> FontOption | None:
        """Look up a font by its id, re-listing if the id isn't in the latest listing.

        Re-listing covers ids from a listing the server no longer holds (after a
        restart) or that a newer listing doesn't have yet.
        """
        with self._lock:
            font = self._fonts_by_id.get(font_id)
        if font is not None:
            return font
        return next((f for f in self.list_fonts() if f.id == font_id), None)

    def render_preview(self, font: FontOption) -> bytes:
        """Render the font's family name in its own face as a transparent PNG.

        Raises OSError if the font can no longer be loaded.
        """
        pil_font = ImageFont.truetype(font.path, size=PREVIEW_FONT_SIZE, index=font.index)
        # Fixed height and baseline so every row of the picker lines up; tall or deep
        # glyphs (script fonts) are clipped rather than shrinking the text.
        left, _top, right, _bottom = pil_font.getbbox(font.family, anchor="ls")
        width = max(1, min(right - left, PREVIEW_MAX_WIDTH))
        image = Image.new("RGBA", (width, PREVIEW_HEIGHT), (0, 0, 0, 0))
        ImageDraw.Draw(image).text(
            (-left, PREVIEW_BASELINE), font.family, font=pil_font, fill=PREVIEW_COLOR, anchor="ls"
        )
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


# Global instance
font_service = FontService()
