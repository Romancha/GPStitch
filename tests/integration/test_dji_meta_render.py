"""Integration tests for full DJI Action render pipeline.

Tests the complete flow: parse DJI meta → convert to GPX → extend time range →
execute wrapper → verify output video.
"""

import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from gpstitch.models.schemas import FileRole


@pytest.mark.integration
@pytest.mark.slow
class TestDjiMetaFullRender:
    """Full rendering pipeline with DJI Action embedded GPS (DJI meta stream).

    These tests perform actual video rendering and are slow.
    Run with: pytest -m "integration and slow" -k "dji_meta"
    """

    @pytest.fixture
    def render_output_dir(self):
        with tempfile.TemporaryDirectory(prefix="gpstitch_dji_meta_test_") as tmpdir:
            yield Path(tmpdir)

    def test_render_dji_action_video_with_embedded_gps(
        self,
        integration_test_dji_action_video,
        render_output_dir,
        clean_file_manager,
        monkeypatch,
    ):
        """Full render: DJI Action video with embedded GPS via gopro-dashboard.

        Verifies:
        1. DJI meta GPS is extracted and converted to GPX
        2. CLI command generates correctly with --use-gpx-only
        3. Wrapper applies DJI meta patch
        4. gopro-dashboard renders successfully
        5. Output video is created with valid dimensions
        """
        import os
        import shutil

        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.dji_meta_parser import parse_dji_meta_file
        from gpstitch.services.metadata import extract_video_metadata
        from gpstitch.services.renderer import generate_cli_command

        # Copy video to temp dir so output doesn't pollute fixtures
        video_copy = render_output_dir / integration_test_dji_action_video.name
        shutil.copy2(integration_test_dji_action_video, video_copy)

        # Set mtime to match GPS timestamps for proper time alignment.
        # file-modified uses mtime as video start time. DJI meta timestamps
        # are treated as UTC by the patch, so set mtime to first GPS timestamp
        # to ensure video dates overlap with GPS data.
        points = parse_dji_meta_file(video_copy)
        first_ts = points[0].timestamp
        from datetime import UTC

        mtime = first_ts.replace(tzinfo=UTC).timestamp()
        os.utime(video_copy, (mtime, mtime))

        # Extract metadata (needed for has_dji_meta detection in generate_cli_command)
        metadata = extract_video_metadata(video_copy)
        assert metadata.has_dji_meta is True

        # Create session with DJI Action video
        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=video_copy.name,
            file_path=str(video_copy),
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=metadata,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        output_file = render_output_dir / "dji_action_render_output.mp4"
        cmd, temp_files = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-1920x1080",
            video_time_alignment="file-modified",
        )

        # Verify command structure
        assert "--use-gpx-only" in cmd
        assert "--gpx" in cmd
        assert "--ts-dji-meta-source" in cmd

        # Execute the render via wrapper
        from gpstitch.scripts import gopro_dashboard_wrapper

        wrapper = Path(gopro_dashboard_wrapper.__file__)
        args = shlex.split(cmd)
        args[0] = str(wrapper)

        result = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode == 0, f"Render failed with exit code {result.returncode}:\n{result.stderr[-2000:]}"
        assert output_file.exists(), "Output file was not created"
        assert output_file.stat().st_size > 0, "Output file is empty"

        # Verify output video dimensions
        probe_result = subprocess.run(
            [
                "ffprobe",
                "-hide_banner",
                "-print_format",
                "json",
                "-show_streams",
                str(output_file),
            ],
            capture_output=True,
            text=True,
        )
        assert probe_result.returncode == 0, f"ffprobe failed: {probe_result.stderr}"

        probe_data = json.loads(probe_result.stdout)
        video_stream = None
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        assert video_stream is not None, "No video stream in output"
        output_w = int(video_stream["width"])
        output_h = int(video_stream["height"])
        assert output_w > 0 and output_h > 0, "Output should have valid dimensions"

        # Clean up temp GPX files created by generate_cli_command
        for f in temp_files:
            Path(f).unlink(missing_ok=True)

    def test_render_dji_action_cli_command_structure(
        self,
        integration_test_dji_action_video,
        render_output_dir,
        clean_file_manager,
        monkeypatch,
    ):
        """Verify CLI command for DJI Action has correct structure and temp GPX exists."""
        import shutil

        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.metadata import extract_video_metadata
        from gpstitch.services.renderer import generate_cli_command

        video_copy = render_output_dir / integration_test_dji_action_video.name
        shutil.copy2(integration_test_dji_action_video, video_copy)

        metadata = extract_video_metadata(video_copy)
        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=video_copy.name,
            file_path=str(video_copy),
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=metadata,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        output_file = render_output_dir / "output.mp4"
        cmd, temp_files = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-1920x1080",
        )

        # Verify command has all required parts
        assert "gopro-dashboard.py" in cmd
        assert "--use-gpx-only" in cmd
        assert "--gpx" in cmd
        assert "--ts-dji-meta-source" in cmd
        assert str(video_copy) in cmd
        assert str(output_file) in cmd

        # Verify temp GPX file was created and contains valid data
        assert len(temp_files) > 0, "Should have temp GPX file"
        gpx_path = Path(temp_files[0])
        assert gpx_path.exists(), f"Temp GPX not found: {gpx_path}"
        assert gpx_path.suffix == ".gpx"

        gpx_content = gpx_path.read_text()
        assert "<trkpt" in gpx_content
        assert "lat=" in gpx_content
        assert "lon=" in gpx_content

        # Clean up
        for f in temp_files:
            Path(f).unlink(missing_ok=True)
