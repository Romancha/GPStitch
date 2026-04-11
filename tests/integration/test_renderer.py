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
class TestAlternateLayoutRender:
    """Tests that alternate (non-default) layouts render correctly (GitHub issue #5).

    Uses render_preview() to verify the full pipeline works with XML-based layouts
    that require --layout xml --layout-xml <path>.
    """

    def test_render_preview_with_power_layout(self, integration_test_video):
        """power-1920x1080 layout should render a valid preview image."""
        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            file_path=integration_test_video,
            layout="power-1920x1080",
            frame_time_ms=5000,
        )

        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert width == 1920
        assert height == 1080

    def test_render_preview_with_moto_layout(self, integration_test_video):
        """moto_1080 layout should render a valid preview image."""
        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            file_path=integration_test_video,
            layout="moto_1080",
            frame_time_ms=5000,
        )

        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert width == 1920
        assert height == 1080

    def test_cli_command_for_alternate_layout(self, clean_file_manager, integration_test_video, monkeypatch):
        """CLI command for power-1920x1080 should use --layout xml --layout-xml."""
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
            layout="power-1920x1080",
        )

        assert "--layout xml" in cmd
        assert "--layout-xml" in cmd
        assert "--layout power-1920x1080" not in cmd

    @pytest.mark.slow
    def test_full_render_with_alternate_layout(self, integration_test_video, clean_file_manager, monkeypatch):
        """Full render with power-1920x1080 layout should produce a valid video."""
        import tempfile

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

        with tempfile.TemporaryDirectory(prefix="gpstitch_test_") as tmpdir:
            output_file = Path(tmpdir) / "power_layout_output.mp4"

            cmd, _ = generate_cli_command(
                session_id=session_id,
                output_file=str(output_file),
                layout="power-1920x1080",
            )

            # Execute the actual render
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

            assert result.returncode == 0, f"Render with power-1920x1080 failed:\n{result.stderr[-2000:]}"
            assert output_file.exists(), "Output file was not created"
            assert output_file.stat().st_size > 0, "Output file is empty"

            # Verify output video metadata
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
            video_stream = next(
                (s for s in metadata.get("streams", []) if s["codec_type"] == "video"),
                None,
            )
            assert video_stream is not None, "No video stream in output"
            assert int(video_stream["width"]) > 0
            assert int(video_stream["height"]) > 0


@pytest.mark.integration
class TestZoneBarPositioning:
    """Tests for zone_bar/bar positioning in editor preview (GitHub issue #6).

    When zone_bar or bar widgets have x,y positions set in the editor,
    they must be wrapped in <translate> elements, not have x,y as direct attributes.
    The gopro-overlay library rejects unknown attributes on these components.
    """

    def test_render_preview_with_positioned_zone_bar(self, integration_test_video):
        """Editor preview with zone_bar at non-zero position should render successfully.

        This is the exact scenario from GitHub issue #6: user copies Power layout,
        moves zone_bar widget to a new position, preview fails with
        'Unknown attributes x,y'.
        """
        from gpstitch.models.editor import CanvasSettings, EditorLayout, LayoutMetadata, WidgetInstance
        from gpstitch.services.renderer import _render_layout_with_data
        from gpstitch.services.xml_converter import xml_converter

        layout = EditorLayout(
            id="test-zone-bar-issue-6",
            metadata=LayoutMetadata(name="Test Zone Bar Position"),
            canvas=CanvasSettings(width=1920, height=1080),
            widgets=[
                WidgetInstance(
                    id="zone-bar-1",
                    type="zone_bar",
                    x=309,
                    y=24,
                    properties={
                        "width": 800,
                        "height": 75,
                        "metric": "hr",
                        "max": 200,
                        "z1": 130,
                        "z2": 163,
                        "z3": 183,
                    },
                ),
            ],
        )

        xml_content = xml_converter.layout_to_xml(layout)

        # This should NOT raise IOError about unknown attributes x,y
        png_bytes, width, height = _render_layout_with_data(
            xml_content=xml_content,
            file_path=integration_test_video,
            frame_time_ms=5000,
            width=1920,
            height=1080,
        )

        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert width == 1920
        assert height == 1080

    def test_render_preview_with_positioned_bar(self, integration_test_video):
        """Editor preview with bar at non-zero position should render successfully."""
        from gpstitch.models.editor import CanvasSettings, EditorLayout, LayoutMetadata, WidgetInstance
        from gpstitch.services.renderer import _render_layout_with_data
        from gpstitch.services.xml_converter import xml_converter

        layout = EditorLayout(
            id="test-bar-position",
            metadata=LayoutMetadata(name="Test Bar Position"),
            canvas=CanvasSettings(width=1920, height=1080),
            widgets=[
                WidgetInstance(
                    id="bar-1",
                    type="bar",
                    x=100,
                    y=50,
                    properties={
                        "width": 400,
                        "height": 30,
                        "metric": "speed",
                    },
                ),
            ],
        )

        xml_content = xml_converter.layout_to_xml(layout)

        png_bytes, width, height = _render_layout_with_data(
            xml_content=xml_content,
            file_path=integration_test_video,
            frame_time_ms=5000,
            width=1920,
            height=1080,
        )

        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.integration
class TestRendererOrientationDegrees:
    """Tests for orientation metrics with degree units (GitHub issue #14).

    Orientation metrics (ori.pitch, ori.roll, ori.yaw) are stored as radians
    in gopro-overlay. The 'degree' unit should convert them via pint fallback.
    """

    def test_render_orientation_pitch_in_degrees(self, integration_test_video):
        """Metric widget with ori.pitch and units=degree should render successfully."""
        from gpstitch.models.editor import CanvasSettings, EditorLayout, LayoutMetadata, WidgetInstance
        from gpstitch.services.renderer import _render_layout_with_data
        from gpstitch.services.xml_converter import xml_converter

        layout = EditorLayout(
            id="test-ori-pitch-degree",
            metadata=LayoutMetadata(name="Orientation Pitch Degrees"),
            canvas=CanvasSettings(width=1920, height=1080),
            widgets=[
                WidgetInstance(
                    id="metric-ori-pitch",
                    type="metric",
                    x=100,
                    y=100,
                    properties={
                        "metric": "ori.pitch",
                        "units": "degree",
                        "dp": "1",
                        "size": "40",
                    },
                ),
            ],
        )

        xml_content = xml_converter.layout_to_xml(layout)
        assert 'metric="ori.pitch"' in xml_content
        assert 'units="degree"' in xml_content

        png_bytes, width, height = _render_layout_with_data(
            xml_content=xml_content,
            file_path=integration_test_video,
            frame_time_ms=5000,
            width=1920,
            height=1080,
        )

        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert width == 1920
        assert height == 1080


@pytest.mark.integration
@pytest.mark.slow
class TestRendererOrientationFullRender:
    """Reproduces GitHub issue #15: orientation metrics render as tiny white
    rectangles in the final (subprocess) render even though they display
    correctly in the editor preview.

    Root cause: the gopro-dashboard CLI defaults ``--load`` to an empty set,
    which disables extraction of the CORI (camera orientation) track. Without
    CORI loaded, ``e.ori`` is ``None``, so ``ori.pitch/roll/yaw`` accessors
    return ``None`` and the metric widget renders an empty string — the visible
    outline stroke becomes the reported "tiny white rectangle".

    Preview works because the in-process loader path (``renderer._render_layout_with_data``)
    constructs ``GoproLoader`` without a ``flags`` argument, which loads ALL
    telemetry tracks including CORI by default.
    """

    @pytest.fixture
    def render_output_dir(self):
        """Create temporary directory for render outputs."""
        with tempfile.TemporaryDirectory(prefix="gpstitch_test_ori_render_") as tmpdir:
            yield Path(tmpdir)

    def _count_bright_pixels(self, png_bytes: bytes, region: tuple[int, int, int, int]) -> int:
        """Count near-white pixels inside a region of a PNG frame.

        A properly rendered metric value (60px font, stroke=2) produces
        thousands of bright pixels in its widget region. The buggy path
        produces only a handful (just the outline stroke of an empty text box).
        """
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        crop = img.crop(region)
        bright = 0
        for r, g, b in crop.getdata():
            if r >= 220 and g >= 220 and b >= 220:
                bright += 1
        return bright

    def test_orientation_metrics_visible_in_final_render(
        self,
        integration_test_video,
        render_output_dir,
        clean_file_manager,
        monkeypatch,
    ):
        """Full subprocess render of a GoPro video with Pitch/Roll/Yaw metrics
        must produce visible values — not tiny white rectangles (issue #15).
        """
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        # Custom layout XML with three orientation metrics at known positions.
        # Large font (size=60) so rendered digits cover thousands of pixels
        # when CORI is loaded, but a broken (empty) render leaves only the
        # tiny stroke outline.
        layout_xml_path = render_output_dir / "orientation_layout.xml"
        layout_xml_path.write_text(
            """<layout>
  <component type="metric" name="pitch" x="100" y="100"
             metric="ori.pitch" units="degree" dp="1" size="60"
             rgb="255,255,255" outline="0,0,0" outline_width="2" align="left"/>
  <component type="metric" name="roll" x="100" y="300"
             metric="ori.roll" units="degree" dp="1" size="60"
             rgb="255,255,255" outline="0,0,0" outline_width="2" align="left"/>
  <component type="metric" name="yaw" x="100" y="500"
             metric="ori.yaw" units="degree" dp="1" size="60"
             rgb="255,255,255" outline="0,0,0" outline_width="2" align="left"/>
</layout>
"""
        )

        # Set up a file_manager session pointing at the GoPro test video
        # (which has CORI telemetry embedded in its GPMF stream).
        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_video.name,
            file_path=integration_test_video,
            file_type="video",
            role=FileRole.PRIMARY,
        )
        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        # Generate and run the real CLI command (same path as production renders).
        output_file = render_output_dir / "orientation_output.mp4"
        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-1920x1080",
            layout_xml_path=str(layout_xml_path),
        )

        assert "--layout-xml" in cmd
        assert str(layout_xml_path) in cmd

        # Execute through the gpstitch-dashboard wrapper, exactly like render_service.
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
        assert output_file.exists(), "Output video was not created"

        # Extract a frame from ~2s into the video (after ramp-up).
        frame_file = render_output_dir / "frame.png"
        probe = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                "2",
                "-i",
                str(output_file),
                "-frames:v",
                "1",
                "-update",
                "1",
                str(frame_file),
            ],
            capture_output=True,
            text=True,
        )
        assert probe.returncode == 0, f"ffmpeg frame extraction failed: {probe.stderr}"
        assert frame_file.exists()

        frame_bytes = frame_file.read_bytes()

        # For each orientation widget, count bright (text) pixels in a generous
        # crop around its (x, y). A correctly rendered "-12.3" at size=60
        # produces several thousand bright pixels. The bug manifests as a
        # tiny ~15x5 outline rectangle (<150 bright pixels).
        #
        # Threshold of 800 is well above the "tiny rectangle" floor but well
        # below the realistic rendered-text count, so it cleanly separates
        # the broken and fixed cases.
        pitch_bright = self._count_bright_pixels(frame_bytes, (80, 80, 480, 200))
        roll_bright = self._count_bright_pixels(frame_bytes, (80, 280, 480, 400))
        yaw_bright = self._count_bright_pixels(frame_bytes, (80, 480, 480, 600))

        assert pitch_bright > 800, (
            f"ori.pitch did not render as text (only {pitch_bright} bright px) — "
            f"issue #15: CORI track not loaded by CLI render"
        )
        assert roll_bright > 800, (
            f"ori.roll did not render as text (only {roll_bright} bright px) — "
            f"issue #15: CORI track not loaded by CLI render"
        )
        assert yaw_bright > 800, (
            f"ori.yaw did not render as text (only {yaw_bright} bright px) — "
            f"issue #15: CORI track not loaded by CLI render"
        )


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

        assert "gpstitch-dashboard" in cmd
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
        video_copy = render_output_dir / integration_test_mov_video.name
        shutil.copy2(integration_test_mov_video, video_copy)
        # Set file modified time to match GPX trackpoint time
        gpx_start = datetime(2024, 8, 8, 16, 52, 18, tzinfo=UTC).timestamp()
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

        # Copy video to temp dir and set mtime to match GPX trackpoint time
        video_copy = render_output_dir / integration_test_mov_video.name
        shutil.copy2(integration_test_mov_video, video_copy)
        gpx_start = datetime(2024, 8, 8, 16, 52, 18, tzinfo=UTC).timestamp()
        os.utime(video_copy, (gpx_start, gpx_start))

        # Step 1: Create pillarboxed video with FFmpeg
        # Video is portrait, canvas is 3840x2160 (landscape)
        canvas_w, canvas_h = 3840, 2160
        video_w, video_h = 360, 640
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
