"""Unit tests for render_service - process cancellation, cleanup, and mtime alignment."""

import asyncio
import datetime
import signal
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCancelRender:
    """Tests for cancel_render method - killing process groups."""

    @pytest.fixture
    def render_service(self):
        """Create a fresh RenderService instance."""
        # Import here to avoid side effects from patches
        from gpstitch.services.render_service import RenderService

        service = RenderService()
        return service

    @pytest.fixture
    def mock_process(self):
        """Create a mock subprocess."""
        process = MagicMock()
        process.pid = 12345
        process.wait = AsyncMock(return_value=0)
        return process

    async def test_cancel_render_wrong_job_id(self, render_service):
        """Cancel returns False if job_id doesn't match current job."""
        render_service._current_job_id = "job-123"

        result = await render_service.cancel_render("job-456")

        assert result is False

    async def test_cancel_render_no_process(self, render_service):
        """Cancel returns False if no process is running."""
        render_service._current_job_id = "job-123"
        render_service._process = None

        result = await render_service.cancel_render("job-123")

        assert result is False

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    async def test_cancel_render_kills_process_group_unix(self, render_service, mock_process):
        """On Unix, cancel_render should kill entire process group."""
        render_service._current_job_id = "job-123"
        render_service._process = mock_process

        with (
            patch("os.killpg") as mock_killpg,
            patch("gpstitch.services.render_service.job_manager") as mock_job_manager,
        ):
            mock_job_manager.update_job_status = AsyncMock()

            result = await render_service.cancel_render("job-123")

            assert result is True
            # Should call killpg with SIGTERM first
            mock_killpg.assert_called_with(12345, signal.SIGTERM)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    async def test_cancel_render_force_kills_on_timeout(self, render_service, mock_process):
        """On timeout, cancel_render should force kill with SIGKILL."""
        render_service._current_job_id = "job-123"
        render_service._process = mock_process

        # Make wait() timeout
        async def slow_wait():
            await asyncio.sleep(10)

        mock_process.wait = slow_wait

        with (
            patch("os.killpg") as mock_killpg,
            patch("gpstitch.services.render_service.job_manager") as mock_job_manager,
        ):
            mock_job_manager.update_job_status = AsyncMock()

            # Use shorter timeout for test
            with patch("asyncio.wait_for", side_effect=TimeoutError):
                # Create a fast completing wait for after SIGKILL
                mock_process.wait = AsyncMock(return_value=0)

                result = await render_service.cancel_render("job-123")

            assert result is True
            # Should have called killpg twice: SIGTERM then SIGKILL
            calls = mock_killpg.call_args_list
            assert len(calls) >= 1
            # Last call should be SIGKILL
            assert any(call[0][1] == signal.SIGKILL for call in calls)

    async def test_cancel_render_handles_process_already_dead(self, render_service, mock_process):
        """Cancel should handle ProcessLookupError gracefully."""
        render_service._current_job_id = "job-123"
        render_service._process = mock_process

        with (
            patch("os.killpg", side_effect=ProcessLookupError),
            patch("gpstitch.services.render_service.job_manager") as mock_job_manager,
        ):
            mock_job_manager.update_job_status = AsyncMock()

            result = await render_service.cancel_render("job-123")

            # Should still return True - process is dead
            assert result is True


class TestKillProcessTree:
    """Tests for _kill_process_tree helper method."""

    @pytest.fixture
    def render_service(self):
        """Create a fresh RenderService instance."""
        from gpstitch.services.render_service import RenderService

        return RenderService()

    @pytest.fixture
    def mock_process(self):
        """Create a mock subprocess."""
        process = MagicMock()
        process.pid = 12345
        process.wait = AsyncMock(return_value=0)
        process.kill = MagicMock()
        return process

    async def test_kill_process_tree_no_process(self, render_service):
        """Should do nothing if no process exists."""
        render_service._process = None

        # Should not raise
        await render_service._kill_process_tree()

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    async def test_kill_process_tree_unix(self, render_service, mock_process):
        """On Unix, should kill entire process group with SIGKILL."""
        render_service._process = mock_process

        with patch("os.killpg") as mock_killpg:
            await render_service._kill_process_tree()

            mock_killpg.assert_called_once_with(12345, signal.SIGKILL)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    async def test_kill_process_tree_windows(self, render_service, mock_process):
        """On Windows, should call process.kill()."""
        render_service._process = mock_process

        await render_service._kill_process_tree()

        mock_process.kill.assert_called_once()

    async def test_kill_process_tree_handles_already_dead(self, render_service, mock_process):
        """Should handle ProcessLookupError gracefully."""
        render_service._process = mock_process

        with patch("os.killpg", side_effect=ProcessLookupError):
            # Should not raise
            await render_service._kill_process_tree()


class TestResolveMtimeForAlignment:
    """Tests for _resolve_mtime_for_alignment method."""

    @pytest.fixture
    def render_service(self):
        from gpstitch.services.render_service import RenderService

        return RenderService()

    @pytest.fixture
    def config(self):
        from gpstitch.models.job import RenderJobConfig

        return RenderJobConfig(
            session_id="test-session",
            layout="default-1920x1080",
            output_file="/tmp/output.mp4",
        )

    def test_auto_mode_with_creation_time(self, render_service, config):
        """Auto mode should return creation_time as Unix timestamp."""
        config.video_time_alignment = "auto"
        creation_time = datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)

        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == creation_time.timestamp()

    def test_auto_mode_fallback_to_ctime(self, render_service, config):
        """Auto mode should fallback to filestat().ctime when no creation_time."""
        config.video_time_alignment = "auto"

        fake_ctime = datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)
        mock_fstat = SimpleNamespace(ctime=fake_ctime)

        with (
            patch(
                "gpstitch.services.renderer._extract_creation_time",
                return_value=None,
            ),
            patch("gopro_overlay.ffmpeg_gopro.filestat", return_value=mock_fstat),
        ):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == fake_ctime.timestamp()

    def test_manual_mode_with_offset(self, render_service, config):
        """Manual mode should add offset to creation_time timestamp."""
        config.video_time_alignment = "manual"
        config.time_offset_seconds = 60
        creation_time = datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)

        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == creation_time.timestamp() + 60

    def test_manual_mode_with_negative_offset(self, render_service, config):
        """Manual mode should support negative offsets."""
        config.video_time_alignment = "manual"
        config.time_offset_seconds = -30
        creation_time = datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)

        with patch(
            "gpstitch.services.renderer._extract_creation_time",
            return_value=creation_time,
        ):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == creation_time.timestamp() - 30

    def test_gpx_timestamps_returns_none(self, render_service, config):
        """GPX-timestamps mode should return None (no mtime change needed)."""
        config.video_time_alignment = "gpx-timestamps"

        ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts is None

    def test_none_alignment_returns_none(self, render_service, config):
        """No alignment should return None."""
        config.video_time_alignment = None

        ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts is None

    def test_file_modified_with_gpx_secondary(self, render_service, config, monkeypatch):
        """file-modified mode with GPX secondary should use GPX start timestamp."""
        config.video_time_alignment = "file-modified"

        mock_secondary = MagicMock()
        mock_secondary.file_type = "gpx"
        mock_secondary.file_path = "/tmp/track.gpx"

        from gpstitch.services import file_manager as fm_module

        mock_fm = MagicMock()
        mock_fm.get_secondary_file.return_value = mock_secondary
        monkeypatch.setattr(fm_module, "file_manager", mock_fm)

        with patch.object(render_service, "_get_gpx_start_timestamp", return_value=1723132380.0):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == 1723132380.0

    def test_file_modified_with_srt_secondary(self, render_service, config, monkeypatch):
        """file-modified mode with SRT secondary should use original video mtime."""
        config.video_time_alignment = "file-modified"

        mock_secondary = MagicMock()
        mock_secondary.file_type = "srt"
        mock_secondary.file_path = "/tmp/telemetry.srt"

        from gpstitch.services import file_manager as fm_module

        mock_fm = MagicMock()
        mock_fm.get_secondary_file.return_value = mock_secondary
        monkeypatch.setattr(fm_module, "file_manager", mock_fm)

        mock_stat = MagicMock()
        mock_stat.st_mtime = 1723132380.0

        with patch("os.stat", return_value=mock_stat):
            ts = render_service._resolve_mtime_for_alignment(config, "/tmp/video.mov")

        assert ts == 1723132380.0


class TestNeedsPillarboxUsesSidecarCanvas:
    """_needs_pillarbox must respect canvas dimensions from a custom XML template's sidecar
    JSON. Without this, a custom 4K 4:3 template (3840x2880) was treated as the default
    built-in layout (1920x1080), which scaled the video down."""

    @pytest.fixture
    def render_service(self):
        from gpstitch.services.render_service import RenderService

        return RenderService()

    def _patch_video_probe(self, monkeypatch, width: int, height: int):
        """Stub gopro-overlay video probing to report the given display dimensions."""
        from gpstitch.services import metadata as metadata_mod

        monkeypatch.setattr(metadata_mod, "get_video_rotation", lambda _p: 0)
        monkeypatch.setattr(metadata_mod, "get_display_dimensions", lambda w, h, _r: (w, h))

        fake_rec = SimpleNamespace(video=SimpleNamespace(dimension=SimpleNamespace(x=width, y=height)))

        class FakeFFMPEGGoPro:
            def __init__(self, *_args, **_kwargs):
                pass

            def find_recording(self, _p):
                return fake_rec

        import gopro_overlay.ffmpeg as gp_ffmpeg
        import gopro_overlay.ffmpeg_gopro as gp_ffmpeg_gopro

        monkeypatch.setattr(gp_ffmpeg, "FFMPEG", lambda: MagicMock())
        monkeypatch.setattr(gp_ffmpeg_gopro, "FFMPEGGoPro", FakeFFMPEGGoPro)

    def test_custom_xml_4k_4_3_no_pillarbox(self, render_service, tmp_path, monkeypatch):
        """Video 3840x2880 with custom XML whose sidecar canvas is 3840x2880 → no pillarbox."""
        xml_path = tmp_path / "Osmo6_Walking_4k_4_3.xml"
        xml_path.write_text("<layout></layout>", encoding="utf-8")
        (tmp_path / "Osmo6_Walking_4k_4_3.json").write_text(
            '{"canvas_width": 3840, "canvas_height": 2880}', encoding="utf-8"
        )

        self._patch_video_probe(monkeypatch, 3840, 2880)

        config = MagicMock()
        config.layout = "xml"
        config.layout_xml_path = str(xml_path)

        result = render_service._needs_pillarbox("/fake/video.mp4", config)
        assert result is None, f"Expected no pillarbox (matching aspect), got {result}"

    def test_custom_xml_canvas_different_aspect_pillarboxes_to_sidecar(self, render_service, tmp_path, monkeypatch):
        """16:9 video into a 4:3 sidecar canvas must pillarbox to the sidecar's dims."""
        xml_path = tmp_path / "custom_4_3.xml"
        xml_path.write_text("<layout></layout>", encoding="utf-8")
        (tmp_path / "custom_4_3.json").write_text('{"canvas_width": 3840, "canvas_height": 2880}', encoding="utf-8")

        self._patch_video_probe(monkeypatch, 3840, 2160)

        config = MagicMock()
        config.layout = "xml"
        config.layout_xml_path = str(xml_path)

        result = render_service._needs_pillarbox("/fake/video.mp4", config)
        assert result is not None
        canvas_w, canvas_h, video_w, video_h = result
        assert (canvas_w, canvas_h) == (3840, 2880)
        assert (video_w, video_h) == (3840, 2160)


class TestStartRenderNonUtf8Layout:
    """A custom layout saved in a non-UTF-8 codec (e.g. GBK from Notepad on Chinese
    Windows) used to raise UnicodeDecodeError out of start_render() after the job slot
    was claimed, wedging the render queue until a server restart."""

    async def test_cairo_check_survives_a_non_utf8_layout(self, tmp_path):
        from gpstitch.models.job import JobStatus
        from gpstitch.services.render_service import RenderService

        xml_path = tmp_path / "custom.xml"
        xml_path.write_bytes('<layout><component type="cairo-circuit-map" name="地图"/></layout>'.encode("gbk"))

        service = RenderService()
        service._start_next_pending_job = AsyncMock()
        config = MagicMock(layout="xml", layout_xml_path=str(xml_path))

        with (
            patch("gpstitch.services.render_service.generate_cli_command", return_value=("cmd", [])),
            patch("gpstitch.constants.is_pycairo_available", return_value=False),
            patch("gpstitch.services.render_service.job_manager") as jm,
        ):
            jm.update_job_status = AsyncMock()
            jm.append_job_log = AsyncMock()
            await service.start_render("job-1", config)

        # The cairo check still ran on the decoded text and failed the job cleanly...
        jm.update_job_status.assert_awaited_once()
        assert jm.update_job_status.await_args.args[:2] == ("job-1", JobStatus.FAILED)
        # ...and released the slot for the next job.
        assert service._current_job_id is None
        service._start_next_pending_job.assert_awaited_once()
