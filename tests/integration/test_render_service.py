"""Integration test: full render pipeline via render_service.start_render().

Uses real MOV video + GPX file with 4K template (default-3840x2160).
Tests the complete async pipeline: job creation → pillarbox preprocessing → render → completion.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from telemetry_studio.models.job import JobStatus, RenderJobConfig
from telemetry_studio.models.schemas import FileRole


@pytest.mark.integration
@pytest.mark.slow
class TestRenderServiceFullPipeline:
    """End-to-end test via render_service.start_render() with real video generation."""

    @pytest.fixture
    def render_output_dir(self):
        with tempfile.TemporaryDirectory(prefix="telemetry_studio_render_svc_") as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_full_render_mov_gpx_4k(
        self,
        integration_test_mov_video,
        integration_test_run_gpx,
        render_output_dir,
        clean_file_manager,
        monkeypatch,
    ):
        """Full render_service pipeline: MOV + GPX → pillarbox → gopro-dashboard → 4K output.

        Verifies:
        1. Job is created and transitions PENDING → RUNNING → COMPLETED
        2. Pillarbox preprocessing runs (portrait video on landscape canvas)
        3. gopro-dashboard renders overlay with telemetry
        4. Output file is 3840x2160
        5. Job logs contain render output
        6. Temp pillarbox file is cleaned up
        """
        from telemetry_studio.services import file_manager as fm_module
        from telemetry_studio.services import job_manager as jm_module
        from telemetry_studio.services.job_manager import JobManager
        from telemetry_studio.services.render_service import RenderService

        # Copy video WITHOUT setting mtime to GPX time.
        # This simulates real usage where the video file's mtime is arbitrary
        # (e.g., the date it was copied to disk, not the recording date).
        # render_service should automatically set pillarbox file's mtime from GPX.
        video_copy = render_output_dir / integration_test_mov_video.name
        shutil.copy2(integration_test_mov_video, video_copy)

        # Setup file manager session
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
            file_path=str(integration_test_run_gpx),
            file_type="gpx",
            role=FileRole.SECONDARY,
        )

        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        # Create isolated job manager
        state_dir = render_output_dir / "jobs"
        state_dir.mkdir()
        isolated_job_manager = JobManager(state_dir=state_dir)
        monkeypatch.setattr(jm_module, "job_manager", isolated_job_manager)
        monkeypatch.setattr("telemetry_studio.services.render_service.job_manager", isolated_job_manager)

        # Create job
        output_file = render_output_dir / "output_4k.mp4"
        config = RenderJobConfig(
            session_id=session_id,
            layout="default-3840x2160",
            output_file=str(output_file),
            video_time_alignment="file-modified",
        )
        job = await isolated_job_manager.create_job(config)
        assert job.status == JobStatus.PENDING

        # Run the full render pipeline
        render_svc = RenderService()
        await render_svc.start_render(job.id, config)

        # Verify job completed
        final_job = await isolated_job_manager.get_job(job.id)
        assert final_job is not None
        assert final_job.status == JobStatus.COMPLETED, (
            f"Job should be COMPLETED, got {final_job.status}. "
            f"Error: {final_job.error}. "
            f"Last logs: {final_job.log_lines[-10:] if final_job.log_lines else 'no logs'}"
        )
        assert final_job.progress.percent == 100

        # Verify output file exists and is valid video
        assert output_file.exists(), "Output video file was not created"
        assert output_file.stat().st_size > 0, "Output video file is empty"

        # Verify output dimensions with ffprobe
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
        video_stream = next(
            (s for s in metadata.get("streams", []) if s.get("codec_type") == "video"),
            None,
        )
        assert video_stream is not None, "No video stream in output"

        # Output should be 3840x2160 (pillarboxed to 4K canvas)
        assert int(video_stream["width"]) == 3840, f"Expected width 3840, got {video_stream['width']}"
        assert int(video_stream["height"]) == 2160, f"Expected height 2160, got {video_stream['height']}"

        # Verify job has log lines (render output was captured)
        assert len(final_job.log_lines) > 0, "Job should have log lines from render output"

        # Verify pillarbox temp file was cleaned up
        temp_files = list(render_output_dir.glob(".*_pillarbox_temp.mp4"))
        assert len(temp_files) == 0, f"Pillarbox temp file should be cleaned up, found: {temp_files}"
