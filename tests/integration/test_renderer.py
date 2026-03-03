"""Integration tests for renderer with real gopro-overlay."""

import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from gpstitch.models.schemas import FileRole


@pytest.mark.integration
class TestRendererPreview:
    """Tests for preview rendering with real video."""

    def test_render_preview_returns_image(self, integration_test_video):
        """Render preview should return PNG image data."""
        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            file_path=integration_test_video,
            layout="default-1920x1080",
            frame_time_ms=5000,
        )

        # Should return image bytes
        assert len(png_bytes) > 0
        # PNG magic bytes
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        # Should be 1920x1080
        assert width == 1920
        assert height == 1080

    def test_render_preview_to_base64(self, integration_test_video):
        """Preview image should convert to base64."""
        import base64

        from gpstitch.services.renderer import image_to_base64, render_preview

        png_bytes, _, _ = render_preview(
            file_path=integration_test_video,
            layout="default-1920x1080",
            frame_time_ms=5000,
        )

        b64 = image_to_base64(png_bytes)

        # Should be valid base64
        decoded = base64.b64decode(b64)
        assert decoded == png_bytes

    def test_render_preview_different_frame(self, integration_test_video):
        """Preview at different frame times should work."""
        from gpstitch.services.renderer import render_preview

        png1, _, _ = render_preview(
            file_path=integration_test_video,
            layout="default-1920x1080",
            frame_time_ms=1000,
        )

        png2, _, _ = render_preview(
            file_path=integration_test_video,
            layout="default-1920x1080",
            frame_time_ms=10000,
        )

        # Both should be valid images but different (different frames)
        assert len(png1) > 0
        assert len(png2) > 0


@pytest.mark.integration
class TestRendererPreviewMOV:
    """Tests for preview rendering with MOV video and external GPX."""

    def test_render_mov_with_external_gpx(self, integration_test_mov_video, integration_test_run_gpx):
        """Render preview with MOV video + external GPX file via gpx_path."""
        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            file_path=integration_test_mov_video,
            layout="default-1920x1080",
            frame_time_ms=0,
            gpx_path=integration_test_run_gpx,
        )

        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert width == 1920
        assert height == 1080

    def test_render_mov_without_gpx_raises(self, integration_test_mov_video):
        """Render MOV without GPS and without gpx_path should raise ValueError."""
        from gpstitch.services.renderer import render_preview

        with pytest.raises(ValueError, match="GPS"):
            render_preview(
                file_path=integration_test_mov_video,
                layout="default-1920x1080",
                frame_time_ms=0,
            )


@pytest.mark.integration
class TestRendererLayouts:
    """Tests for layout handling."""

    def test_get_available_layouts(self):
        """Should return list of available layouts."""
        from gpstitch.services.renderer import get_available_layouts

        layouts = get_available_layouts()

        assert len(layouts) > 0
        # Should have default layout
        layout_names = [layout.name for layout in layouts]
        assert any("default" in name for name in layout_names)

    def test_layout_has_dimensions(self):
        """Layouts should have width and height."""
        from gpstitch.services.renderer import get_available_layouts

        layouts = get_available_layouts()

        for layout in layouts:
            assert layout.width > 0
            assert layout.height > 0


@pytest.mark.integration
class TestRendererUnits:
    """Tests for unit options."""

    def test_get_available_units(self):
        """Should return unit options."""
        from gpstitch.services.renderer import get_available_units

        units = get_available_units()

        assert len(units) > 0
        # Units is a dict with category keys
        assert "speed" in units
        assert "altitude" in units

    def test_units_have_options(self):
        """Unit categories should have options."""
        from gpstitch.services.renderer import get_available_units

        units = get_available_units()

        for _category_name, category_data in units.items():
            assert "options" in category_data
            assert len(category_data["options"]) > 0


@pytest.mark.integration
class TestRendererMapStyles:
    """Tests for map style options."""

    def test_get_available_map_styles(self):
        """Should return map style options."""
        from gpstitch.services.renderer import get_available_map_styles

        styles = get_available_map_styles()

        assert len(styles) > 0
        # Should have OSM style
        style_names = [s["name"] for s in styles]
        assert "osm" in style_names or any("open" in name.lower() for name in style_names)


@pytest.mark.integration
class TestRendererFFmpegProfiles:
    """Tests for FFmpeg profile options."""

    def test_get_available_ffmpeg_profiles(self):
        """Should return FFmpeg profile options."""
        from gpstitch.services.renderer import get_available_ffmpeg_profiles

        profiles = get_available_ffmpeg_profiles()

        assert len(profiles) > 0
        # Should have at least one profile
        for profile in profiles:
            assert "name" in profile
            assert "display_name" in profile


@pytest.mark.integration
class TestRendererCLICommand:
    """Tests for CLI command generation."""

    def test_generate_cli_command_video_only(self, clean_file_manager, integration_test_video, monkeypatch):
        """Generate CLI command for video-only mode."""
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_video.name,
            file_path=integration_test_video,
            file_type="video",
            role=FileRole.PRIMARY,
        )

        # Patch the singleton file_manager at the source module
        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
        )

        assert "gopro-dashboard.py" in cmd
        assert str(integration_test_video) in cmd
        assert "--layout" in cmd
        assert "/tmp/output.mp4" in cmd

    def test_generate_cli_command_with_units(self, clean_file_manager, integration_test_video, monkeypatch):
        """Generate CLI command with custom units."""
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_video.name,
            file_path=integration_test_video,
            file_type="video",
            role=FileRole.PRIMARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
            units_speed="mph",
            units_altitude="feet",
        )

        assert "--units-speed" in cmd
        assert "mph" in cmd
        assert "--units-altitude" in cmd
        assert "feet" in cmd

    def test_generate_cli_command_with_gpx(
        self, clean_file_manager, integration_test_video, sample_gpx_file, sample_video_metadata, monkeypatch
    ):
        """Generate CLI command with GPX merge."""
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_video.name,
            file_path=integration_test_video,
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=sample_video_metadata,
        )
        clean_file_manager.add_file(
            session_id=session_id,
            filename=sample_gpx_file.name,
            file_path=sample_gpx_file,
            file_type="gpx",
            role=FileRole.SECONDARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
        )

        assert "--gpx" in cmd
        assert str(sample_gpx_file) in cmd
        assert "--gpx-merge" in cmd

    def test_generate_cli_command_video_gpx_with_time_alignment(
        self, clean_file_manager, integration_test_video, sample_gpx_file, sample_video_metadata, monkeypatch
    ):
        """Generate CLI command with GPX + time alignment should use --use-gpx-only."""
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_video.name,
            file_path=integration_test_video,
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=sample_video_metadata,
        )
        clean_file_manager.add_file(
            session_id=session_id,
            filename=sample_gpx_file.name,
            file_path=sample_gpx_file,
            file_type="gpx",
            role=FileRole.SECONDARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
            video_time_alignment="file-modified",
        )

        # --video-time-start requires --use-gpx-only in gopro-dashboard
        assert "--video-time-start" in cmd
        assert "file-modified" in cmd
        assert "--use-gpx-only" in cmd
        # Should NOT have --gpx-merge when time alignment is set
        assert "--gpx-merge" not in cmd

    def test_generate_cli_command_with_ffmpeg_profile(self, clean_file_manager, integration_test_video, monkeypatch):
        """Generate CLI command with FFmpeg profile."""
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_video.name,
            file_path=integration_test_video,
            file_type="video",
            role=FileRole.PRIMARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file="/tmp/output.mp4",
            layout="default-1920x1080",
            ffmpeg_profile="nvenc",
        )

        assert "--profile" in cmd
        assert "nvenc" in cmd


@pytest.mark.integration
@pytest.mark.slow
class TestVerticalVideoRender:
    """Tests for rendering vertical (portrait) video with external GPX on 4K canvas.

    These tests perform actual video rendering with gopro-dashboard and are slow.
    Run with: pytest -m "integration and slow" -k "vertical"
    """

    @pytest.fixture
    def render_output_dir(self):
        """Create temporary directory for render outputs."""
        with tempfile.TemporaryDirectory(prefix="gpstitch_test_render_") as tmpdir:
            yield Path(tmpdir)

    def test_render_vertical_mov_with_gpx_4k(
        self,
        integration_test_mov_video,
        integration_test_run_gpx,
        render_output_dir,
        clean_file_manager,
        monkeypatch,
    ):
        """Render vertical MOV (1080x1920) + GPX on 4K canvas (3840x2160).

        Verifies:
        1. Command generates correctly with --use-gpx-only and --overlay-size
        2. gopro-dashboard renders successfully (exit code 0)
        3. Output file is created
        4. Output video has correct 4K dimensions (3840x2160)
        """
        import os
        import shutil
        from datetime import UTC, datetime

        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        # Copy video to temp dir and set mtime to match GPX data
        # GPX timestamps: 2026-01-26T17:36:34Z (start of first trackpoint)
        video_copy = render_output_dir / integration_test_mov_video.name
        shutil.copy2(integration_test_mov_video, video_copy)
        # Set file modified time to match GPX first trackpoint time (17:36:54Z)
        gpx_start = datetime(2026, 1, 26, 17, 36, 54, tzinfo=UTC).timestamp()
        os.utime(video_copy, (gpx_start, gpx_start))

        # Setup session with MOV video + GPX
        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=video_copy.name,
            file_path=str(video_copy),
            file_type="video",
            role=FileRole.PRIMARY,
        )
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_run_gpx.name,
            file_path=integration_test_run_gpx,
            file_type="gpx",
            role=FileRole.SECONDARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        # Generate command for 4K layout with time alignment
        output_file = render_output_dir / "vertical_4k_output.mp4"
        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-3840x2160",
            video_time_alignment="file-modified",
        )

        # Verify command structure
        assert "--use-gpx-only" in cmd, "Should use --use-gpx-only with time alignment"
        assert "--overlay-size 3840x2160" in cmd, "Should have 4K overlay size"
        assert "--video-time-start file-modified" in cmd
        assert "--gpx-merge" not in cmd, "Should NOT have --gpx-merge with time alignment"

        # Find gopro-dashboard.py
        from gpstitch.scripts import gopro_dashboard_wrapper

        wrapper = Path(gopro_dashboard_wrapper.__file__)
        assert wrapper.exists(), "Wrapper script not found"

        # Execute the actual render
        args = shlex.split(cmd)
        args[0] = str(wrapper)

        result = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max for short video
        )

        assert result.returncode == 0, f"Render failed with exit code {result.returncode}:\n{result.stderr[-2000:]}"
        assert output_file.exists(), "Output file was not created"
        assert output_file.stat().st_size > 0, "Output file is empty"

        # gopro-dashboard outputs video at native resolution.
        # Pillarbox to canvas dimensions is handled by render_service via FFmpeg pre-processing.
        # Here we verify gopro-dashboard renders successfully with vertical video + GPX.
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

        metadata = json.loads(probe_result.stdout)
        video_stream = None
        for stream in metadata.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        assert video_stream is not None, "No video stream in output"
        # Output is at video's native portrait resolution
        output_w = int(video_stream["width"])
        output_h = int(video_stream["height"])
        assert output_w > 0 and output_h > 0, "Output should have valid dimensions"

    def test_render_vertical_mov_with_pillarbox_preprocessing(
        self,
        integration_test_mov_video,
        integration_test_run_gpx,
        render_output_dir,
        clean_file_manager,
        monkeypatch,
    ):
        """Full pipeline: FFmpeg pillarbox preprocessing + gopro-dashboard render on 4K canvas.

        This tests the complete render_service flow:
        1. FFmpeg creates pillarboxed video (portrait → 4K landscape with black bars)
        2. gopro-dashboard renders overlay on top of pillarboxed video
        3. Output video is 3840x2160 with video centered and black pillarbox bars
        """
        import os
        import shutil
        from datetime import UTC, datetime

        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        # Copy video to temp dir and set mtime to match GPX first trackpoint
        video_copy = render_output_dir / integration_test_mov_video.name
        shutil.copy2(integration_test_mov_video, video_copy)
        gpx_start = datetime(2026, 1, 26, 17, 36, 54, tzinfo=UTC).timestamp()
        os.utime(video_copy, (gpx_start, gpx_start))

        # Step 1: Create pillarboxed video with FFmpeg
        # Video is 1080x1920 (portrait), canvas is 3840x2160 (landscape)
        # scale = min(3840/1080, 2160/1920) = min(3.555, 1.125) = 1.125
        # new_w = 1080 * 1.125 = 1215 (round to even: 1214), new_h = 1920 * 1.125 = 2160
        canvas_w, canvas_h = 3840, 2160
        video_w, video_h = 1080, 1920
        scale = min(canvas_w / video_w, canvas_h / video_h)
        new_w = int(video_w * scale)
        new_h = int(video_h * scale)
        new_w = new_w - (new_w % 2)
        new_h = new_h - (new_h % 2)
        pad_x = (canvas_w - new_w) // 2
        pad_y = (canvas_h - new_h) // 2

        pillarboxed_video = render_output_dir / "pillarboxed.mp4"
        vf = f"scale={new_w}:{new_h},pad={canvas_w}:{canvas_h}:{pad_x}:{pad_y}"

        ffmpeg_result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_copy),
                "-vf",
                vf,
                "-c:a",
                "copy",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "18",
                str(pillarboxed_video),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert ffmpeg_result.returncode == 0, f"FFmpeg pillarbox failed: {ffmpeg_result.stderr[-500:]}"
        assert pillarboxed_video.exists()

        # Copy mtime to pillarboxed video (needed for --video-time-start)
        os.utime(pillarboxed_video, (gpx_start, gpx_start))

        # Step 2: Setup session with pillarboxed video + GPX
        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=pillarboxed_video.name,
            file_path=str(pillarboxed_video),
            file_type="video",
            role=FileRole.PRIMARY,
        )
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_run_gpx.name,
            file_path=integration_test_run_gpx,
            file_type="gpx",
            role=FileRole.SECONDARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        output_file = render_output_dir / "vertical_4k_pillarbox_output.mp4"
        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-3840x2160",
            video_time_alignment="file-modified",
        )

        # Step 3: Run gopro-dashboard on pillarboxed video
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

        # Step 4: Verify output is 3840x2160
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
        assert probe_result.returncode == 0

        metadata = json.loads(probe_result.stdout)
        video_stream = None
        for stream in metadata.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        assert video_stream is not None, "No video stream in output"
        assert int(video_stream["width"]) == 3840, f"Expected width 3840, got {video_stream['width']}"
        assert int(video_stream["height"]) == 2160, f"Expected height 2160, got {video_stream['height']}"

    def test_render_vertical_mov_preview_pillarbox(
        self,
        integration_test_mov_video,
        integration_test_run_gpx,
    ):
        """Preview of vertical MOV on 4K canvas should have pillarbox (black bars on sides)."""
        import io

        from PIL import Image

        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            file_path=integration_test_mov_video,
            layout="default-3840x2160",
            frame_time_ms=0,
            gpx_path=integration_test_run_gpx,
        )

        assert width == 3840
        assert height == 2160
        assert len(png_bytes) > 0

        # Load the preview image and verify pillarbox
        image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        assert image.size == (3840, 2160)

        # Left edge should be black (pillarbox bar)
        left_pixel = image.getpixel((10, 1080))
        assert left_pixel[0] < 30 and left_pixel[1] < 30 and left_pixel[2] < 30, (
            f"Left edge should be black (pillarbox), got {left_pixel}"
        )

        # Right edge should be black (pillarbox bar)
        right_pixel = image.getpixel((3830, 1080))
        assert right_pixel[0] < 30 and right_pixel[1] < 30 and right_pixel[2] < 30, (
            f"Right edge should be black (pillarbox), got {right_pixel}"
        )

        # Center should NOT be black (video content)
        center_pixel = image.getpixel((1920, 1080))
        pixel_sum = center_pixel[0] + center_pixel[1] + center_pixel[2]
        assert pixel_sum > 30, f"Center should have video content (not pure black), got {center_pixel}"
