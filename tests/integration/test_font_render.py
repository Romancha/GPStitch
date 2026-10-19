"""Real renders with a user-selected overlay font (issue #25): the font must reach the video."""

import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from gpstitch.models.schemas import FileRole
from tests.fixtures.data import install_sample_font


@pytest.fixture(scope="module")
def render_frame(integration_test_video, tmp_path_factory):
    """Render the GoPro fixture with a font and return one frame of the output."""
    from gpstitch.scripts import gopro_dashboard_wrapper
    from gpstitch.services import file_manager as fm_module
    from gpstitch.services.metadata import extract_video_metadata
    from gpstitch.services.renderer import generate_cli_command

    out_dir = tmp_path_factory.mktemp("font_render")
    session_id = fm_module.file_manager.create_local_session()
    fm_module.file_manager.add_file(
        session_id=session_id,
        filename=integration_test_video.name,
        file_path=integration_test_video,
        file_type="video",
        role=FileRole.PRIMARY,
        video_metadata=extract_video_metadata(integration_test_video),
    )

    def render(name: str, font: str | None = None, font_index: int = 0) -> Image.Image:
        output_file = out_dir / f"{name}.mp4"
        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-1920x1080",
            font=font,
            font_index=font_index,
        )
        args = shlex.split(cmd)
        args[0] = str(Path(gopro_dashboard_wrapper.__file__))
        result = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=600)
        assert result.returncode == 0, f"Render failed:\n{(result.stdout + result.stderr)[-3000:]}"

        frame = out_dir / f"{name}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", "1.5", "-i", str(output_file), "-frames:v", "1", str(frame)],
            check=True,
        )
        return Image.open(frame).convert("RGB")

    yield render
    fm_module.file_manager.cleanup_session(session_id)


def _differs(a: Image.Image, b: Image.Image) -> bool:
    """True if the frames differ by more than encoding noise (i.e. the overlay text changed)."""
    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 64 else 0)
    return diff.getbbox() is not None


def _collection_with_two_faces() -> tuple[str, int] | None:
    """An installed .ttc and a face index other than 0, if the system has one."""
    from gpstitch.services.font_service import FontService

    for font in FontService().list_fonts():
        if font.index > 0:
            return font.path, font.index
    return None


@pytest.mark.integration
@pytest.mark.slow
class TestFontRender:
    def test_selected_font_is_drawn(self, render_frame, tmp_path):
        font = str(install_sample_font(tmp_path / "JetBrainsMono.ttf"))

        assert _differs(render_frame("auto"), render_frame("jetbrains", font))

    def test_collection_face_index_is_drawn(self, render_frame):
        collection = _collection_with_two_faces()
        if collection is None:
            pytest.skip("No installed font collection with several faces")
        path, index = collection

        # Without the wrapper patch every index renders face 0
        assert _differs(render_frame("face0", path, 0), render_frame(f"face{index}", path, index))
