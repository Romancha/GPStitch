"""Tests for batch render with shared GPX support."""

from unittest.mock import patch

import pytest

from gpstitch.api.render import BatchFileInput, BatchRenderRequest


class TestBatchRenderRequestModel:
    """Tests for BatchRenderRequest model validation."""

    def test_shared_gpx_path_default_none(self):
        req = BatchRenderRequest(files=[BatchFileInput(video_path="/tmp/video.mp4")])
        assert req.shared_gpx_path is None

    def test_shared_gpx_path_set(self):
        req = BatchRenderRequest(
            files=[BatchFileInput(video_path="/tmp/video.mp4")],
            shared_gpx_path="/tmp/track.gpx",
        )
        assert req.shared_gpx_path == "/tmp/track.gpx"

    def test_shared_gpx_path_with_multiple_files(self):
        req = BatchRenderRequest(
            files=[
                BatchFileInput(video_path="/tmp/v1.mp4"),
                BatchFileInput(video_path="/tmp/v2.mp4"),
                BatchFileInput(video_path="/tmp/v3.mp4"),
            ],
            shared_gpx_path="/tmp/shared.gpx",
        )
        assert req.shared_gpx_path == "/tmp/shared.gpx"
        assert len(req.files) == 3

    def test_per_file_gpx_coexists_with_shared(self):
        req = BatchRenderRequest(
            files=[
                BatchFileInput(video_path="/tmp/v1.mp4", gpx_path="/tmp/per_file.gpx"),
                BatchFileInput(video_path="/tmp/v2.mp4"),
            ],
            shared_gpx_path="/tmp/shared.gpx",
        )
        assert req.files[0].gpx_path == "/tmp/per_file.gpx"
        assert req.files[1].gpx_path is None
        assert req.shared_gpx_path == "/tmp/shared.gpx"


class TestBatchRenderSharedGpx:
    """Tests for start_batch_render endpoint with shared_gpx_path."""

    @pytest.fixture
    def batch_video_files(self, temp_dir):
        """Create multiple dummy video files."""
        videos = []
        for i in range(3):
            path = temp_dir / f"video_{i}.mp4"
            path.write_bytes(b"fake video")
            videos.append(path)
        return videos

    @pytest.fixture
    def shared_gpx_file(self, temp_dir):
        """Create a shared GPX file."""
        gpx_path = temp_dir / "shared_track.gpx"
        gpx_path.write_text(
            '<?xml version="1.0"?><gpx><trk><trkseg></trkseg></trk></gpx>',
            encoding="utf-8",
        )
        return gpx_path

    @pytest.mark.anyio
    async def test_shared_gpx_applied_to_all_files(self, async_client, batch_video_files, shared_gpx_file):
        """Shared GPX should be applied as secondary file to all videos without per-file GPX."""
        response = await async_client.post(
            "/api/render/batch",
            json={
                "files": [{"video_path": str(v)} for v in batch_video_files],
                "shared_gpx_path": str(shared_gpx_file),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 3
        assert len(data["job_ids"]) == 3
        assert len(data["skipped_files"]) == 0

        # Verify each job has the shared GPX as secondary file
        from gpstitch.services.file_manager import file_manager
        from gpstitch.services.job_manager import job_manager

        for job_id in data["job_ids"]:
            job = await job_manager.get_job(job_id)
            assert job is not None
            secondary = file_manager.get_secondary_file(job.config.session_id)
            assert secondary is not None
            assert secondary.file_path == str(shared_gpx_file.resolve())

    @pytest.mark.anyio
    async def test_per_file_gpx_overrides_shared(self, async_client, batch_video_files, shared_gpx_file, temp_dir):
        """Per-file GPX should take priority over shared GPX."""
        per_file_gpx = temp_dir / "per_file.gpx"
        per_file_gpx.write_text(
            '<?xml version="1.0"?><gpx><trk><trkseg></trkseg></trk></gpx>',
            encoding="utf-8",
        )

        response = await async_client.post(
            "/api/render/batch",
            json={
                "files": [
                    {"video_path": str(batch_video_files[0]), "gpx_path": str(per_file_gpx)},
                    {"video_path": str(batch_video_files[1])},
                ],
                "shared_gpx_path": str(shared_gpx_file),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 2

        from gpstitch.services.file_manager import file_manager
        from gpstitch.services.job_manager import job_manager

        # First file should use per-file GPX
        job0 = await job_manager.get_job(data["job_ids"][0])
        sec0 = file_manager.get_secondary_file(job0.config.session_id)
        assert sec0 is not None
        assert sec0.file_path == str(per_file_gpx.resolve())

        # Second file should use shared GPX
        job1 = await job_manager.get_job(data["job_ids"][1])
        sec1 = file_manager.get_secondary_file(job1.config.session_id)
        assert sec1 is not None
        assert sec1.file_path == str(shared_gpx_file.resolve())

    @pytest.mark.anyio
    async def test_no_shared_gpx_no_per_file_gpx(self, async_client, batch_video_files):
        """Without shared or per-file GPX, no secondary file should be added."""
        response = await async_client.post(
            "/api/render/batch",
            json={
                "files": [{"video_path": str(v)} for v in batch_video_files],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 3

        from gpstitch.services.file_manager import file_manager
        from gpstitch.services.job_manager import job_manager

        for job_id in data["job_ids"]:
            job = await job_manager.get_job(job_id)
            secondary = file_manager.get_secondary_file(job.config.session_id)
            assert secondary is None

    @pytest.mark.anyio
    async def test_shared_gpx_nonexistent_file(self, async_client, batch_video_files):
        """Non-existent shared GPX should be silently skipped (warning logged)."""
        response = await async_client.post(
            "/api/render/batch",
            json={
                "files": [{"video_path": str(batch_video_files[0])}],
                "shared_gpx_path": "/nonexistent/path/track.gpx",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 1

        from gpstitch.services.file_manager import file_manager
        from gpstitch.services.job_manager import job_manager

        job = await job_manager.get_job(data["job_ids"][0])
        secondary = file_manager.get_secondary_file(job.config.session_id)
        assert secondary is None


class TestBatchRenderOdoOffset:
    """Tests for odo_offset calculation in batch render with shared GPX."""

    @pytest.fixture
    def batch_video_files(self, temp_dir):
        videos = []
        for i in range(2):
            path = temp_dir / f"video_{i}.mp4"
            path.write_bytes(b"fake video")
            videos.append(path)
        return videos

    @pytest.fixture
    def shared_gpx_file(self, temp_dir):
        gpx_path = temp_dir / "shared_track.gpx"
        gpx_path.write_text(
            '<?xml version="1.0"?><gpx><trk><trkseg></trkseg></trk></gpx>',
            encoding="utf-8",
        )
        return gpx_path

    @pytest.mark.anyio
    async def test_odo_offset_stored_in_job_config(self, async_client, batch_video_files, shared_gpx_file):
        """When shared GPX is used and creation time is available, odo_offset should be set."""
        import datetime

        mock_creation_time = datetime.datetime(2024, 7, 1, 10, 0, 1, tzinfo=datetime.UTC)

        with (
            patch("gpstitch.services.renderer._extract_creation_time", return_value=mock_creation_time),
            patch("gpstitch.services.renderer.calculate_odo_offset", return_value=1234.5),
        ):
            response = await async_client.post(
                "/api/render/batch",
                json={
                    "files": [{"video_path": str(v)} for v in batch_video_files],
                    "shared_gpx_path": str(shared_gpx_file),
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 2

        from gpstitch.services.job_manager import job_manager

        for job_id in data["job_ids"]:
            job = await job_manager.get_job(job_id)
            assert job.config.odo_offset == 1234.5

    @pytest.mark.anyio
    async def test_odo_offset_none_when_no_creation_time(self, async_client, batch_video_files, shared_gpx_file):
        """When creation time cannot be extracted, odo_offset should be None."""
        with patch("gpstitch.services.renderer._extract_creation_time", return_value=None):
            response = await async_client.post(
                "/api/render/batch",
                json={
                    "files": [{"video_path": str(v)} for v in batch_video_files],
                    "shared_gpx_path": str(shared_gpx_file),
                },
            )

        assert response.status_code == 200
        data = response.json()

        from gpstitch.services.job_manager import job_manager

        for job_id in data["job_ids"]:
            job = await job_manager.get_job(job_id)
            assert job.config.odo_offset is None

    @pytest.mark.anyio
    async def test_odo_offset_none_without_shared_gpx(self, async_client, batch_video_files):
        """Without shared GPX, odo_offset should be None."""
        response = await async_client.post(
            "/api/render/batch",
            json={
                "files": [{"video_path": str(v)} for v in batch_video_files],
            },
        )

        assert response.status_code == 200
        data = response.json()

        from gpstitch.services.job_manager import job_manager

        for job_id in data["job_ids"]:
            job = await job_manager.get_job(job_id)
            assert job.config.odo_offset is None

    @pytest.mark.anyio
    async def test_odo_offset_not_set_for_per_file_gpx(self, async_client, batch_video_files, shared_gpx_file, temp_dir):
        """Per-file GPX should NOT trigger odo_offset calculation (only shared GPX does)."""
        per_file_gpx = temp_dir / "per_file.gpx"
        per_file_gpx.write_text(
            '<?xml version="1.0"?><gpx><trk><trkseg></trkseg></trk></gpx>',
            encoding="utf-8",
        )

        response = await async_client.post(
            "/api/render/batch",
            json={
                "files": [
                    {"video_path": str(batch_video_files[0]), "gpx_path": str(per_file_gpx)},
                ],
                "shared_gpx_path": str(shared_gpx_file),
            },
        )

        assert response.status_code == 200
        data = response.json()

        from gpstitch.services.job_manager import job_manager

        # Per-file GPX overrides shared, so odo_offset should be None
        job = await job_manager.get_job(data["job_ids"][0])
        assert job.config.odo_offset is None
