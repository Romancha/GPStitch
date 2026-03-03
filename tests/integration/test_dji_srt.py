"""Integration tests for DJI SRT telemetry: parsing, GPX conversion, and rendering."""

import json
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import pytest

from gpstitch.models.schemas import FileRole
from gpstitch.services.srt_parser import (
    calc_sample_rate,
    estimate_srt_fps,
    get_srt_metadata,
    load_srt_timeseries,
    parse_srt,
    srt_to_gpx_file,
)


@pytest.mark.integration
class TestDjiSrtParsingReal:
    """Parse real DJI SRT file and validate extracted data."""

    def test_parse_real_srt_returns_points(self, integration_test_dji_srt):
        points = parse_srt(integration_test_dji_srt)
        assert len(points) > 0

    def test_parse_real_srt_coordinates_valid(self, integration_test_dji_srt):
        points = parse_srt(integration_test_dji_srt)
        for point in points:
            assert -90 <= point.lat <= 90, f"Invalid latitude: {point.lat}"
            assert -180 <= point.lon <= 180, f"Invalid longitude: {point.lon}"

    def test_parse_real_srt_timestamps_monotonic(self, integration_test_dji_srt):
        points = parse_srt(integration_test_dji_srt)
        for i in range(1, len(points)):
            assert points[i].dt >= points[i - 1].dt, (
                f"Timestamps not monotonic at index {i}: {points[i - 1].dt} > {points[i].dt}"
            )

    def test_parse_real_srt_altitude_present(self, integration_test_dji_srt):
        points = parse_srt(integration_test_dji_srt)
        # At least some points should have non-zero abs_alt
        abs_alts = [p.abs_alt for p in points]
        assert any(a != 0.0 for a in abs_alts), "Expected non-zero abs_alt in real SRT data"

    def test_estimate_fps_around_30(self, integration_test_dji_srt):
        fps = estimate_srt_fps(integration_test_dji_srt)
        # DJI drones typically shoot at ~30fps
        assert 25 <= fps <= 60, f"Unexpected FPS estimate: {fps}"

    def test_metadata_returns_valid_info(self, integration_test_dji_srt):
        meta = get_srt_metadata(integration_test_dji_srt)
        assert meta["gps_point_count"] > 0
        assert meta["duration_seconds"] is not None
        assert meta["duration_seconds"] > 0


@pytest.mark.integration
class TestDjiSrtToGpxConversion:
    """Convert real DJI SRT to GPX and validate the output."""

    def test_srt_to_gpx_creates_valid_file(self, integration_test_dji_srt, tmp_path):
        output = tmp_path / "dji_test.gpx"
        result = srt_to_gpx_file(integration_test_dji_srt, output)

        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0

    def test_gpx_is_valid_xml(self, integration_test_dji_srt, tmp_path):
        output = tmp_path / "dji_test.gpx"
        srt_to_gpx_file(integration_test_dji_srt, output)

        tree = ElementTree.parse(output)
        root = tree.getroot()
        assert "gpx" in root.tag

    def test_gpx_contains_all_trackpoints(self, integration_test_dji_srt, tmp_path):
        points = parse_srt(integration_test_dji_srt)
        output = tmp_path / "dji_test.gpx"
        srt_to_gpx_file(integration_test_dji_srt, output)

        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        tree = ElementTree.parse(output)
        trkpts = tree.findall(".//gpx:trkpt", ns)
        assert len(trkpts) == len(points)

    def test_gpx_coordinates_match_srt(self, integration_test_dji_srt, tmp_path):
        points = parse_srt(integration_test_dji_srt)
        output = tmp_path / "dji_test.gpx"
        srt_to_gpx_file(integration_test_dji_srt, output)

        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        tree = ElementTree.parse(output)
        trkpts = tree.findall(".//gpx:trkpt", ns)

        first_trkpt = trkpts[0]
        assert float(first_trkpt.get("lat")) == pytest.approx(points[0].lat, abs=1e-5)
        assert float(first_trkpt.get("lon")) == pytest.approx(points[0].lon, abs=1e-5)

    def test_gpx_has_elevation_and_time(self, integration_test_dji_srt, tmp_path):
        output = tmp_path / "dji_test.gpx"
        srt_to_gpx_file(integration_test_dji_srt, output)

        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        tree = ElementTree.parse(output)
        trkpts = tree.findall(".//gpx:trkpt", ns)

        for trkpt in trkpts:
            ele = trkpt.find("gpx:ele", ns)
            time = trkpt.find("gpx:time", ns)
            assert ele is not None, "Missing <ele> element"
            assert time is not None, "Missing <time> element"
            assert ele.text is not None
            assert time.text is not None

    def test_gpx_with_sampling_reduces_points(self, integration_test_dji_srt, tmp_path):
        points = parse_srt(integration_test_dji_srt)
        output = tmp_path / "dji_test_sampled.gpx"

        fps = estimate_srt_fps(integration_test_dji_srt)
        sample_rate = calc_sample_rate(fps, 1)
        srt_to_gpx_file(integration_test_dji_srt, output, sample_rate=sample_rate)

        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        tree = ElementTree.parse(output)
        trkpts = tree.findall(".//gpx:trkpt", ns)

        # Sampled GPX should have significantly fewer points than raw SRT
        assert len(trkpts) < len(points)
        # points[::sample_rate] gives ceil(len/sample_rate) points
        expected_max = (len(points) + sample_rate - 1) // sample_rate
        assert len(trkpts) <= expected_max


@pytest.mark.integration
class TestDjiSrtTimezoneOffset:
    """Test timezone offset estimation between SRT local time and video UTC mtime."""

    def test_estimate_tz_offset_returns_nonzero(self, integration_test_dji_srt, integration_test_dji_video):
        """Timezone offset should be detected from video mtime vs SRT timestamps."""
        from gpstitch.services.srt_parser import estimate_tz_offset

        offset, mtime_role = estimate_tz_offset(integration_test_dji_srt, integration_test_dji_video)
        assert offset is not None, "Offset should be determined for valid SRT"
        # Offset should be a whole number of hours
        assert offset.total_seconds() % 3600 == 0
        assert mtime_role in ("start", "end")

    def test_gpx_timestamps_match_video_mtime_after_correction(
        self, integration_test_dji_srt, integration_test_dji_video, tmp_path
    ):
        """After tz_offset correction, the matching SRT point should be close to video mtime."""
        import os

        from gpstitch.services.srt_parser import (
            estimate_tz_offset,
            parse_srt,
        )

        offset, mtime_role = estimate_tz_offset(integration_test_dji_srt, integration_test_dji_video)
        assert offset is not None, "Offset should be determined for valid SRT"
        points = parse_srt(integration_test_dji_srt)

        # Use first or last SRT point depending on detected mtime role
        corrected = points[0].dt - offset if mtime_role == "start" else points[-1].dt - offset

        # Compare as naive datetimes (both represent UTC after correction)
        from datetime import UTC

        mtime_utc = datetime.fromtimestamp(os.stat(integration_test_dji_video).st_mtime, tz=UTC)
        mtime_naive = mtime_utc.replace(tzinfo=None)

        # Corrected SRT timestamp should be within 2 seconds of video mtime
        diff = abs((corrected - mtime_naive).total_seconds())
        assert diff < 2.0, (
            f"Corrected timestamp {corrected} too far from mtime {mtime_naive}: {diff}s (mtime_role={mtime_role})"
        )


@pytest.mark.integration
class TestDjiSrtTimeseries:
    """Load real SRT into gopro_overlay Timeseries."""

    def test_load_srt_timeseries(self, integration_test_dji_srt):
        from gopro_overlay.units import units

        ts = load_srt_timeseries(integration_test_dji_srt, units)
        entries = ts.items()
        assert len(entries) > 0

    def test_load_srt_timeseries_with_sampling(self, integration_test_dji_srt):
        from gopro_overlay.units import units

        ts_full = load_srt_timeseries(integration_test_dji_srt, units, sample_rate=1)
        ts_sampled = load_srt_timeseries(integration_test_dji_srt, units, sample_rate=10)

        assert len(ts_sampled.items()) < len(ts_full.items())


@pytest.mark.integration
class TestDjiSrtPreviewRender:
    """Render preview images using DJI video + SRT telemetry."""

    def test_render_preview_dji_video_with_srt(self, integration_test_dji_video, integration_test_dji_srt):
        """Render preview with DJI video + SRT as external telemetry source."""
        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            file_path=integration_test_dji_video,
            layout="default-1920x1080",
            frame_time_ms=0,
            gpx_path=integration_test_dji_srt,
        )

        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert width == 1920
        assert height == 1080

    def test_render_preview_srt_only(self, integration_test_dji_srt):
        """Render preview using SRT file as primary (overlay-only mode)."""
        from gpstitch.services.renderer import render_preview

        png_bytes, width, height = render_preview(
            file_path=integration_test_dji_srt,
            layout="default-1920x1080",
            frame_time_ms=0,
        )

        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert width == 1920
        assert height == 1080


@pytest.mark.integration
class TestDjiSrtCliCommand:
    """Generate and validate CLI commands for DJI SRT rendering."""

    def test_cli_command_video_with_srt_secondary(
        self, clean_file_manager, integration_test_dji_video, integration_test_dji_srt, monkeypatch
    ):
        """CLI command for DJI video + SRT should convert SRT to GPX."""
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_dji_video.name,
            file_path=str(integration_test_dji_video),
            file_type="video",
            role=FileRole.PRIMARY,
        )
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_dji_srt.name,
            file_path=str(integration_test_dji_srt),
            file_type="srt",
            role=FileRole.SECONDARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file="/tmp/dji_output.mp4",
            layout="default-1920x1080",
            video_time_alignment="file-modified",
        )

        assert "gopro-dashboard.py" in cmd
        # SRT should be converted to GPX — command should reference .gpx not .srt
        assert "--gpx" in cmd
        assert ".gpx" in cmd
        assert "--use-gpx-only" in cmd
        # DJI SRT with file-modified should use --video-time-start or --video-time-end
        # depending on detected mtime role (varies by DJI model)
        has_time_start = "--video-time-start file-modified" in cmd
        has_time_end = "--video-time-end file-modified" in cmd
        assert has_time_start or has_time_end, f"Expected --video-time-start or --video-time-end in: {cmd}"

    def test_cli_command_srt_primary_only(self, clean_file_manager, integration_test_dji_srt, monkeypatch):
        """CLI command for SRT-only mode should convert to GPX and use --use-gpx-only."""
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_dji_srt.name,
            file_path=str(integration_test_dji_srt),
            file_type="srt",
            role=FileRole.PRIMARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file="/tmp/dji_overlay_output.mp4",
            layout="default-1920x1080",
        )

        assert "gopro-dashboard.py" in cmd
        assert "--use-gpx-only" in cmd
        assert "--gpx" in cmd
        assert ".gpx" in cmd


@pytest.mark.integration
@pytest.mark.slow
class TestDjiSrtFullRender:
    """Full rendering pipeline with DJI video + SRT telemetry.

    These tests perform actual video rendering and are slow.
    Run with: pytest -m "integration and slow" -k "dji"
    """

    @pytest.fixture
    def render_output_dir(self):
        with tempfile.TemporaryDirectory(prefix="gpstitch_dji_test_") as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.xfail(
        reason=(
            "Test DJI video is only ~0.8s. gopro-dashboard's DateRange.overlap_seconds() "
            "returns int(delta) which truncates 0.8s to 0, failing the overlap check. "
            "Needs a test video >= 1.1s to pass. Non-slow tests cover SRT→GPX, preview, "
            "timeseries, and CLI command generation."
        ),
        strict=False,
    )
    def test_render_dji_video_with_srt(
        self,
        integration_test_dji_video,
        integration_test_dji_srt,
        render_output_dir,
        clean_file_manager,
        monkeypatch,
    ):
        """Full render: DJI video + SRT telemetry via gopro-dashboard.

        Verifies:
        1. SRT is converted to GPX
        2. CLI command generates correctly
        3. gopro-dashboard renders successfully
        4. Output video is created with valid dimensions
        """
        import os
        import shutil

        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command
        from gpstitch.services.srt_parser import parse_srt, srt_to_gpx_file

        # Convert SRT to GPX with sample_rate=1 (keep all points)
        # The test SRT is very short (~0.8s, 25 frames), so no thinning
        srt_points = parse_srt(integration_test_dji_srt)
        gpx_output = render_output_dir / "dji_telemetry.gpx"
        srt_to_gpx_file(integration_test_dji_srt, gpx_output, sample_rate=1)

        # Extend GPX time range by adding a point 2s after the last one.
        # gopro-dashboard requires strict time overlap between video and GPX,
        # and the test SRT is only ~0.8s, which causes edge cases.
        gpx_content = gpx_output.read_text()
        last_point = srt_points[-1]
        extra_point = (
            f'<trkpt lat="{last_point.lat:.6f}" lon="{last_point.lon:.6f}">'
            f"<ele>{last_point.rel_alt:.1f}</ele>"
            f"<time>{(last_point.dt.replace(second=last_point.dt.second + 2)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}</time>"
            f"</trkpt>"
        )
        gpx_content = gpx_content.replace("</trkseg>", f"{extra_point}</trkseg>")
        gpx_output.write_text(gpx_content)

        video_copy = render_output_dir / integration_test_dji_video.name
        shutil.copy2(integration_test_dji_video, video_copy)

        # Set mtime 1 second after SRT start for file-modified alignment.
        # gopro-dashboard uses mtime as a reference and requires strict overlap.
        srt_start_ts = srt_points[0].dt.timestamp() + 1
        os.utime(video_copy, (srt_start_ts, srt_start_ts))

        # Use the pre-converted GPX (not SRT) to avoid auto-sampling
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
            filename=gpx_output.name,
            file_path=str(gpx_output),
            file_type="gpx",
            role=FileRole.SECONDARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        output_file = render_output_dir / "dji_srt_render_output.mp4"
        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-1920x1080",
            video_time_alignment="file-modified",
        )

        # Execute the render
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

        metadata = json.loads(probe_result.stdout)
        video_stream = None
        for stream in metadata.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        assert video_stream is not None, "No video stream in output"
        output_w = int(video_stream["width"])
        output_h = int(video_stream["height"])
        assert output_w > 0 and output_h > 0, "Output should have valid dimensions"
