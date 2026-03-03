"""Unit tests for JobManager service."""

from datetime import UTC, datetime, timedelta

from gpstitch.models.job import JobStatus


class TestJobManagerCreate:
    """Tests for job creation."""

    async def test_create_job_generates_id(self, clean_job_manager, sample_job_config):
        """Created job should have a UUID."""
        job = await clean_job_manager.create_job(sample_job_config)

        assert job.id
        assert len(job.id) == 36

    async def test_create_job_status_pending(self, clean_job_manager, sample_job_config):
        """New job should have PENDING status."""
        job = await clean_job_manager.create_job(sample_job_config)

        assert job.status == JobStatus.PENDING

    async def test_create_job_persisted(self, clean_job_manager, sample_job_config):
        """Job should be persisted to disk."""
        job = await clean_job_manager.create_job(sample_job_config)
        job_file = clean_job_manager._job_file_path(job.id)

        assert job_file.exists()

    async def test_create_job_stores_config(self, clean_job_manager, sample_job_config):
        """Job should store configuration."""
        job = await clean_job_manager.create_job(sample_job_config)

        assert job.config.layout == sample_job_config.layout
        assert job.config.output_file == sample_job_config.output_file

    async def test_create_job_with_batch(self, clean_job_manager, sample_job_config):
        """Create job with batch ID."""
        batch_id = "batch-123"

        job = await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)

        assert job.batch_id == batch_id


class TestJobManagerQuery:
    """Tests for job queries."""

    async def test_get_job(self, clean_job_manager, sample_job_config):
        """Get job by ID."""
        job = await clean_job_manager.create_job(sample_job_config)

        retrieved = await clean_job_manager.get_job(job.id)

        assert retrieved is not None
        assert retrieved.id == job.id

    async def test_get_job_nonexistent(self, clean_job_manager):
        """Get nonexistent job returns None."""
        result = await clean_job_manager.get_job("nonexistent")

        assert result is None

    async def test_list_jobs(self, clean_job_manager, sample_job_config):
        """List jobs returns all jobs."""
        job1 = await clean_job_manager.create_job(sample_job_config)
        job2 = await clean_job_manager.create_job(sample_job_config)

        jobs = await clean_job_manager.list_jobs()

        assert len(jobs) >= 2
        job_ids = [j.id for j in jobs]
        assert job1.id in job_ids
        assert job2.id in job_ids

    async def test_list_jobs_newest_first(self, clean_job_manager, sample_job_config):
        """List jobs should return newest first."""
        await clean_job_manager.create_job(sample_job_config)
        job2 = await clean_job_manager.create_job(sample_job_config)

        jobs = await clean_job_manager.list_jobs()

        # job2 created after job1, should be first
        assert jobs[0].id == job2.id

    async def test_get_next_pending_job_fifo(self, clean_job_manager, sample_job_config):
        """Get next pending job in FIFO order."""
        job1 = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.create_job(sample_job_config)

        next_job = await clean_job_manager.get_next_pending_job()

        assert next_job.id == job1.id  # First created

    async def test_has_pending_jobs(self, clean_job_manager, sample_job_config):
        """Check if there are pending jobs."""
        assert not await clean_job_manager.has_pending_jobs()

        await clean_job_manager.create_job(sample_job_config)

        assert await clean_job_manager.has_pending_jobs()

    async def test_has_active_job(self, clean_job_manager, sample_job_config):
        """Check if there's an active job."""
        assert not await clean_job_manager.has_active_job()

        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        assert await clean_job_manager.has_active_job()

    async def test_get_current_job(self, clean_job_manager, sample_job_config):
        """Get currently running job."""
        job = await clean_job_manager.create_job(sample_job_config)

        # No current job initially
        assert await clean_job_manager.get_current_job() is None

        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        current = await clean_job_manager.get_current_job()
        assert current is not None
        assert current.id == job.id


class TestJobManagerUpdate:
    """Tests for job updates."""

    async def test_update_job_status_to_running(self, clean_job_manager, sample_job_config):
        """Update job status to RUNNING sets started_at."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.RUNNING
        assert updated.started_at is not None

    async def test_update_job_status_to_completed(self, clean_job_manager, sample_job_config):
        """Update job status to COMPLETED sets completed_at."""
        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        await clean_job_manager.update_job_status(job.id, JobStatus.COMPLETED)

        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.COMPLETED
        assert updated.completed_at is not None

    async def test_update_job_status_with_error(self, clean_job_manager, sample_job_config):
        """Update job status with error message."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.update_job_status(job.id, JobStatus.FAILED, error="Test error")

        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.FAILED
        assert updated.error == "Test error"

    async def test_update_job_progress(self, clean_job_manager, sample_job_config):
        """Update job progress."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.update_job_progress(
            job.id,
            percent=50.0,
            current_frame=500,
            total_frames=1000,
            fps=30.0,
            eta_seconds=16.7,
        )

        updated = await clean_job_manager.get_job(job.id)
        assert updated.progress.percent == 50.0
        assert updated.progress.current_frame == 500
        assert updated.progress.total_frames == 1000
        assert updated.progress.fps == 30.0
        assert updated.progress.eta_seconds == 16.7

    async def test_update_job_progress_capped_at_100(self, clean_job_manager, sample_job_config):
        """Progress should be capped at 100%."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.update_job_progress(job.id, percent=150.0)

        updated = await clean_job_manager.get_job(job.id)
        assert updated.progress.percent == 100.0

    async def test_append_job_log(self, clean_job_manager, sample_job_config):
        """Append log lines to job."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.append_job_log(job.id, "Line 1")
        await clean_job_manager.append_job_log(job.id, "Line 2")

        updated = await clean_job_manager.get_job(job.id)
        assert "Line 1" in updated.log_lines
        assert "Line 2" in updated.log_lines

    async def test_append_job_log_truncates_at_500(self, clean_job_manager, sample_job_config):
        """Log should be truncated to 500 lines max."""
        job = await clean_job_manager.create_job(sample_job_config)

        # Add 600 lines
        for i in range(600):
            await clean_job_manager.append_job_log(job.id, f"Line {i}")

        updated = await clean_job_manager.get_job(job.id)
        assert len(updated.log_lines) == 500
        assert "Line 599" in updated.log_lines  # Latest should be kept

    async def test_set_job_pid(self, clean_job_manager, sample_job_config):
        """Set process ID for job."""
        job = await clean_job_manager.create_job(sample_job_config)

        await clean_job_manager.set_job_pid(job.id, 12345)

        updated = await clean_job_manager.get_job(job.id)
        assert updated.pid == 12345


class TestJobManagerBatch:
    """Tests for batch job operations."""

    async def test_count_batch_jobs(self, clean_job_manager, sample_job_config):
        """Count jobs in a batch."""
        batch_id = "batch-test"

        await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)
        await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)
        await clean_job_manager.create_job(sample_job_config)  # Different batch

        counts = await clean_job_manager.count_batch_jobs(batch_id)

        assert counts["total"] == 2
        assert counts["pending"] == 2
        assert counts["running"] == 0
        assert counts["completed"] == 0

    async def test_cancel_batch_pending_jobs(self, clean_job_manager, sample_job_config):
        """Cancel all pending jobs in batch."""
        batch_id = "batch-cancel"

        job1 = await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)
        job2 = await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)

        cancelled = await clean_job_manager.cancel_batch_pending_jobs(batch_id)

        assert cancelled == 2

        job1_updated = await clean_job_manager.get_job(job1.id)
        job2_updated = await clean_job_manager.get_job(job2.id)

        assert job1_updated.status == JobStatus.CANCELLED
        assert job2_updated.status == JobStatus.CANCELLED

    async def test_get_running_batch_job(self, clean_job_manager, sample_job_config):
        """Get running job in batch."""
        batch_id = "batch-running"

        job = await clean_job_manager.create_job_with_batch(sample_job_config, batch_id)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)

        running = await clean_job_manager.get_running_batch_job(batch_id)

        assert running is not None
        assert running.id == job.id


class TestJobManagerCleanup:
    """Tests for cleanup operations."""

    async def test_cleanup_old_jobs(self, clean_job_manager, sample_job_config):
        """Cleanup old completed jobs."""
        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.COMPLETED)

        # Manually set completed_at to old date
        updated_job = await clean_job_manager.get_job(job.id)
        updated_job.completed_at = datetime.now(UTC) - timedelta(hours=48)
        clean_job_manager._persist_job(updated_job)

        cleaned = await clean_job_manager.cleanup_old_jobs(max_age_hours=24)

        assert cleaned == 1
        assert await clean_job_manager.get_job(job.id) is None

    async def test_cleanup_old_jobs_keeps_fresh(self, clean_job_manager, sample_job_config):
        """Fresh completed jobs are not cleaned."""
        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.COMPLETED)

        cleaned = await clean_job_manager.cleanup_old_jobs(max_age_hours=24)

        assert cleaned == 0
        assert await clean_job_manager.get_job(job.id) is not None

    async def test_cleanup_orphaned_pending_jobs(self, clean_job_manager, sample_job_config):
        """Cleanup pending jobs with nonexistent sessions."""
        job = await clean_job_manager.create_job(sample_job_config)

        # Valid sessions don't include job's session
        valid_sessions = {"other-session-1", "other-session-2"}

        cleaned = await clean_job_manager.cleanup_orphaned_pending_jobs(valid_sessions)

        assert cleaned == 1
        updated = await clean_job_manager.get_job(job.id)
        assert updated.status == JobStatus.FAILED
        assert "orphaned" in updated.error.lower()


class TestJobManagerPersistence:
    """Tests for job persistence and recovery."""

    async def test_job_survives_restart(self, clean_job_manager, sample_job_config, temp_dir):
        """Jobs should be loadable after simulated restart."""
        from gpstitch.services.job_manager import JobManager

        job = await clean_job_manager.create_job(sample_job_config)
        job_id = job.id

        # Create new manager with same state_dir
        new_manager = JobManager(state_dir=clean_job_manager.state_dir)

        restored = await new_manager.get_job(job_id)

        assert restored is not None
        assert restored.config.session_id == sample_job_config.session_id

    async def test_running_job_marked_failed_on_restart(self, clean_job_manager, sample_job_config, temp_dir):
        """Running jobs should be marked as failed on restart."""
        from gpstitch.services.job_manager import JobManager

        job = await clean_job_manager.create_job(sample_job_config)
        await clean_job_manager.update_job_status(job.id, JobStatus.RUNNING)
        job_id = job.id

        # Create new manager (simulates restart)
        new_manager = JobManager(state_dir=clean_job_manager.state_dir)

        restored = await new_manager.get_job(job_id)

        assert restored.status == JobStatus.FAILED
        assert "restarted" in restored.error.lower()
