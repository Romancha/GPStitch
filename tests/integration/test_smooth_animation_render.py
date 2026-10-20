"""Real renders with smooth animation (issue #26): the overlay must follow the video timeline.

Raising only ffmpeg's -framerate made the overlay play too fast and run out of data
part-way through the video; these tests check the drawn frame count and timing.
"""

import datetime
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from gpstitch.models.schemas import FileRole


def _render(cmd: str) -> str:
    """Run a gpstitch-dashboard command through the wrapper and return its output."""
    from gpstitch.scripts import gopro_dashboard_wrapper

    args = shlex.split(cmd)
    args[0] = str(Path(gopro_dashboard_wrapper.__file__))
    result = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=600)
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"Render failed:\n{output[-3000:]}"
    return output


def _drawn_frames(output: str) -> int:
    match = re.search(r"Timer\(drawing frames - Called: ([\d,]+)", output)
    assert match, "draw timer not found in render output"
    return int(match.group(1).replace(",", ""))


def _probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=avg_frame_rate,nb_read_frames:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _write_gpx(path: Path, seconds: int) -> None:
    start = datetime.datetime(2026, 6, 1, 10, 0, 0, tzinfo=datetime.UTC)
    points = "".join(
        f'<trkpt lat="{52.36 + i * 0.0001:.6f}" lon="{4.88 + i * 0.0001:.6f}"><ele>10</ele>'
        f"<time>{(start + datetime.timedelta(seconds=i)).strftime('%Y-%m-%dT%H:%M:%SZ')}</time></trkpt>"
        for i in range(seconds + 1)
    )
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><trkseg>{points}</trkseg></trk></gpx>",
        encoding="utf-8",
    )


def _smooth_command(file_manager, monkeypatch, path: Path, file_type: str, output_file: Path, **file_kwargs) -> str:
    """Command for a session holding just path, rendered with smooth animation."""
    from gpstitch.services import file_manager as fm_module
    from gpstitch.services.renderer import generate_cli_command

    session_id = file_manager.create_local_session()
    file_manager.add_file(
        session_id=session_id,
        filename=path.name,
        file_path=path,
        file_type=file_type,
        role=FileRole.PRIMARY,
        **file_kwargs,
    )
    monkeypatch.setattr(fm_module, "file_manager", file_manager)
    cmd, _ = generate_cli_command(
        session_id=session_id, output_file=str(output_file), layout="default-1920x1080", smooth_animation=True
    )
    return cmd


@pytest.mark.integration
class TestProbeVideoFrameRate:
    def test_real_video(self, integration_test_video):
        from gpstitch.services.renderer import _probe_video_frame_rate

        assert _probe_video_frame_rate(integration_test_video) == pytest.approx(25.0)

    def test_not_a_video(self, temp_dir):
        from gpstitch.services.renderer import _probe_video_frame_rate

        path = temp_dir / "broken.mp4"
        path.write_bytes(b"not a video")
        assert _probe_video_frame_rate(path) is None


@pytest.mark.integration
@pytest.mark.slow
class TestSmoothAnimationRender:
    def test_video_overlay_drawn_at_video_frame_rate(
        self, integration_test_video, temp_dir, clean_file_manager, monkeypatch
    ):
        from gpstitch.services.metadata import extract_video_metadata

        metadata = extract_video_metadata(integration_test_video)
        output_file = temp_dir / "smooth.mp4"
        cmd = _smooth_command(
            clean_file_manager, monkeypatch, integration_test_video, "video", output_file, video_metadata=metadata
        )
        assert "--ts-overlay-fps 25" in cmd

        output = _render(cmd)
        # The default layout's moving map is drawn through the smooth map patch
        assert "Smooth map patch applied" in output

        # One overlay frame per video frame over the telemetry span, not 10 per second
        expected = metadata.duration_seconds * metadata.frame_rate
        assert _drawn_frames(output) == pytest.approx(expected, abs=3)
        # The output keeps the video's frames; like a stock 10 FPS render, the overlay
        # stream may run one frame past the end of the video
        output_frames = int(_probe(output_file)["streams"][0]["nb_read_frames"])
        assert metadata.frame_count <= output_frames <= metadata.frame_count + 1

    def test_overlay_only_render_at_30_fps_keeps_track_duration(self, temp_dir, clean_file_manager, monkeypatch):
        gpx_path = temp_dir / "track.gpx"
        _write_gpx(gpx_path, seconds=6)
        output_file = temp_dir / "overlay.mp4"
        cmd = _smooth_command(clean_file_manager, monkeypatch, gpx_path, "gpx", output_file)
        assert "--ts-overlay-fps 30" in cmd

        _render(cmd)

        probe = _probe(output_file)
        assert probe["streams"][0]["avg_frame_rate"] == "30/1"
        assert int(probe["streams"][0]["nb_read_frames"]) == pytest.approx(6 * 30, abs=1)
        assert float(probe["format"]["duration"]) == pytest.approx(6.0, abs=0.1)
