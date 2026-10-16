"""Tests for the smooth animation option: job config and --ts-overlay-fps in generated commands."""

import logging
from unittest.mock import MagicMock

import pytest

from gpstitch.models.job import RenderJobConfig
from gpstitch.services import renderer
from gpstitch.services.renderer import generate_cli_command
from tests.fixtures.factories import create_file_info, create_video_metadata


@pytest.fixture
def session_with(monkeypatch, temp_dir):
    """Install a file manager whose primary file has the given type and frame rate."""

    def install(file_type: str = "video", frame_rate: float | None = 30.0):
        path = temp_dir / ("track.gpx" if file_type == "gpx" else "video.mp4")
        path.write_bytes(b"fake")
        metadata = create_video_metadata(frame_rate=frame_rate) if frame_rate is not None else None
        primary = create_file_info(
            filename=path.name, file_path=str(path), file_type=file_type, video_metadata=metadata
        )

        file_manager = MagicMock()
        file_manager.get_files.return_value = [primary]
        file_manager.get_primary_file.return_value = primary
        file_manager.get_secondary_file.return_value = None
        monkeypatch.setattr("gpstitch.services.file_manager.file_manager", file_manager)

    return install


def _command(**kwargs) -> str:
    cmd, _ = generate_cli_command(session_id="test", output_file="/tmp/out.mp4", layout="default-1920x1080", **kwargs)
    return cmd


def test_old_job_json_without_option_loads():
    config = RenderJobConfig.model_validate_json('{"session_id": "s", "layout": "default", "output_file": "o.mp4"}')
    assert config.smooth_animation is False


class TestGenerateCliCommandOverlayFps:
    def test_absent_by_default(self, session_with):
        session_with(frame_rate=59.94)
        assert "--ts-overlay-fps" not in _command()

    def test_uses_video_frame_rate(self, session_with):
        session_with(frame_rate=30000 / 1001)
        assert _command(smooth_animation=True).endswith("--ts-overlay-fps 29.97003")

    @pytest.mark.parametrize(("frame_rate", "expected"), [(25.0, "25"), (60.0, "60"), (119.88, "60"), (240.0, "60")])
    def test_follows_frame_rate_capped_at_60_fps(self, session_with, frame_rate, expected):
        session_with(frame_rate=frame_rate)
        assert f"--ts-overlay-fps {expected}" in _command(smooth_animation=True)

    @pytest.mark.parametrize("frame_rate", [5.0, 10.0])
    def test_never_below_stock_10_fps(self, session_with, frame_rate):
        session_with(frame_rate=frame_rate)
        assert "--ts-overlay-fps" not in _command(smooth_animation=True)

    def test_overlay_only_render_uses_30_fps(self, session_with):
        session_with(file_type="gpx")
        assert "--ts-overlay-fps 30" in _command(smooth_animation=True)

    def test_probes_video_without_metadata(self, session_with, monkeypatch):
        """Batch render sessions are created without video metadata."""
        session_with(frame_rate=None)
        probe = MagicMock(return_value=50.0)
        monkeypatch.setattr(renderer, "_probe_video_frame_rate", probe)

        assert "--ts-overlay-fps 50" in _command(smooth_animation=True)
        probe.assert_called_once()

    def test_unknown_frame_rate_falls_back_to_10_fps(self, session_with, monkeypatch, caplog):
        session_with(frame_rate=None)
        monkeypatch.setattr(renderer, "_probe_video_frame_rate", MagicMock(return_value=None))

        with caplog.at_level(logging.WARNING, logger="gpstitch.services.renderer"):
            cmd = _command(smooth_animation=True)

        assert "--ts-overlay-fps" not in cmd
        assert any(record.levelno == logging.WARNING for record in caplog.records)
