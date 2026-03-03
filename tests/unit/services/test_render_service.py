"""Unit tests for render_service - process cancellation and cleanup."""

import asyncio
import signal
import sys
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
