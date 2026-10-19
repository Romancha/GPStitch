"""Tests for the user-selected overlay font in preview and the generated command."""

from unittest.mock import MagicMock, patch

import pytest
from PIL import ImageFont

from gpstitch.models.job import RenderJobConfig
from gpstitch.services import renderer
from gpstitch.services.renderer import _find_available_font, _load_font_with_fallback, generate_cli_command


@pytest.fixture
def collection_faces():
    """Make every font load as a collection with faces 0-2, like macOS Helvetica.ttc."""
    real_truetype = ImageFont.truetype

    def fake_truetype(font=None, size=10, index=0, **kwargs):
        if index > 2:
            raise OSError("invalid face index")
        return real_truetype(font=font, size=size, **kwargs)

    with patch.object(renderer.ImageFont, "truetype", side_effect=fake_truetype) as truetype:
        yield truetype


@pytest.fixture
def video_session(monkeypatch):
    from gpstitch.models.schemas import FileInfo, FileRole
    from gpstitch.services import file_manager as fm_module

    manager = MagicMock()
    primary = FileInfo(filename="video.mp4", file_path="/tmp/video.mp4", file_type="video", role=FileRole.PRIMARY)
    manager.get_files.return_value = [primary]
    manager.get_primary_file.return_value = primary
    manager.get_secondary_file.return_value = None
    monkeypatch.setattr(fm_module, "file_manager", manager)


def _command(**kwargs) -> str:
    cmd, _ = generate_cli_command(session_id="test", output_file="/tmp/out.mp4", layout="default-1920x1080", **kwargs)
    return cmd


def test_old_job_json_without_font_loads():
    config = RenderJobConfig.model_validate_json('{"session_id": "s", "layout": "default", "output_file": "o.mp4"}')
    assert config.font is None
    assert config.font_index == 0


class TestFindAvailableFont:
    def test_selected_font_wins(self, sample_font):
        assert _find_available_font(sample_font) == (sample_font, 0)

    def test_selected_face_of_collection(self, sample_font, collection_faces):
        assert _find_available_font(sample_font, 2) == (sample_font, 2)

    def test_uninstalled_font_falls_back_to_auto(self, tmp_path):
        missing = str(tmp_path / "Gone.ttf")

        assert _find_available_font(missing) == _find_available_font()

    def test_missing_face_falls_back_to_auto(self, sample_font, collection_faces):
        assert _find_available_font(sample_font, 7) == _find_available_font()


class TestLoadFontWithFallback:
    def test_loads_selected_face(self, sample_font, collection_faces):
        _load_font_with_fallback(sample_font, 1)

        collection_faces.assert_called_with(font=sample_font, size=32, index=1)

    def test_loaded_font_is_selected_font(self, sample_font):
        assert _load_font_with_fallback(sample_font).getname() == ("JetBrains Mono", "Regular")


class TestGenerateCliCommandFont:
    def test_selected_font_is_passed(self, video_session, sample_font):
        cmd = _command(font=sample_font)

        assert f"--font {sample_font}" in cmd
        assert "--ts-font-index" not in cmd

    def test_face_index_is_passed_to_wrapper(self, video_session, sample_font, collection_faces):
        cmd = _command(font=sample_font, font_index=2)

        assert f"--font {sample_font} --ts-font-index 2" in cmd

    def test_uninstalled_font_is_not_passed(self, video_session, tmp_path):
        missing = str(tmp_path / "Gone.ttf")

        cmd = _command(font=missing, font_index=1)

        assert missing not in cmd
        assert "--ts-font-index" not in cmd
        assert cmd == _command()
