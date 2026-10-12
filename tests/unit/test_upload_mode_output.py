"""Unit tests for upload mode: mtime preservation, persistent render output, download."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from gpstitch.api.render import default_output_path
from gpstitch.api.upload import _restore_mtime


class TestRestoreMtime:
    """Uploaded copies must keep the original mtime - DJI SRT time alignment relies on it."""

    def test_applies_browser_last_modified(self, tmp_path):
        path = tmp_path / "DJI_0001.MP4"
        path.write_bytes(b"video")
        recorded_at_ms = 1_791_639_812_000  # 2026-10-10T13:43:32Z

        _restore_mtime(path, recorded_at_ms)

        assert os.stat(path).st_mtime == recorded_at_ms / 1000

    def test_missing_value_keeps_current_mtime(self, tmp_path):
        path = tmp_path / "DJI_0001.MP4"
        path.write_bytes(b"video")
        before = os.stat(path).st_mtime

        _restore_mtime(path, None)

        assert os.stat(path).st_mtime == before

    def test_invalid_value_does_not_raise(self, tmp_path):
        path = tmp_path / "DJI_0001.MP4"
        path.write_bytes(b"video")

        _restore_mtime(path, 10**30)


class TestDefaultOutputPath:
    """Renders of uploaded files must not land in the temporary session dir."""

    def test_local_session_renders_next_to_source(self, tmp_path):
        source = tmp_path / "clip.mp4"

        result = default_output_path("local:abc", str(source), ".mp4")

        assert result == str(tmp_path / "clip_overlay.mp4")

    def test_upload_session_renders_to_output_dir(self, tmp_path):
        output_dir = tmp_path / "renders"
        with patch("gpstitch.api.render.settings", SimpleNamespace(output_dir=output_dir)):
            result = default_output_path("abc-123", "/tmp/session/clip.mp4", ".mp4")

        assert result == str(output_dir / "clip_overlay.mp4")
        assert output_dir.is_dir()

    def test_upload_session_does_not_overwrite_previous_render(self, tmp_path):
        output_dir = tmp_path / "renders"
        output_dir.mkdir()
        (output_dir / "clip_overlay.mp4").write_bytes(b"first")
        (output_dir / "clip_overlay_1.mp4").write_bytes(b"second")

        with patch("gpstitch.api.render.settings", SimpleNamespace(output_dir=output_dir)):
            result = default_output_path("abc-123", "/tmp/session/clip.mp4", ".mp4")

        assert result == str(output_dir / "clip_overlay_2.mp4")


class TestDownloadOutput:
    """GET /api/render/download/{job_id} serves the finished render."""

    def _job(self, status, output_file):
        return SimpleNamespace(status=SimpleNamespace(value=status), config=SimpleNamespace(output_file=output_file))

    async def test_downloads_completed_render(self, async_client, tmp_path):
        output = tmp_path / "clip_overlay.mp4"
        output.write_bytes(b"rendered")
        job = self._job("completed", str(output))

        with patch("gpstitch.api.render.job_manager.get_job", AsyncMock(return_value=job)):
            response = await async_client.get("/api/render/download/job-1")

        assert response.status_code == 200
        assert response.content == b"rendered"
        assert "clip_overlay.mp4" in response.headers["content-disposition"]

    async def test_running_render_is_not_downloadable(self, async_client, tmp_path):
        job = self._job("running", str(tmp_path / "clip_overlay.mp4"))

        with patch("gpstitch.api.render.job_manager.get_job", AsyncMock(return_value=job)):
            response = await async_client.get("/api/render/download/job-1")

        assert response.status_code == 409

    async def test_unknown_job_returns_404(self, async_client):
        with patch("gpstitch.api.render.job_manager.get_job", AsyncMock(return_value=None)):
            response = await async_client.get("/api/render/download/missing")

        assert response.status_code == 404
