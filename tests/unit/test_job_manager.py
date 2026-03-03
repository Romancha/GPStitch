"""Unit tests for JobManager batch functionality."""

from pathlib import Path

import pytest

from gpstitch.models.job import JobStatus, RenderJobConfig
from gpstitch.services.job_manager import JobManager


@pytest.fixture
def job_manager_instance(tmp_path: Path) -> JobManager:
    """Create a fresh JobManager with isolated state directory."""
    return JobManager(state_dir=tmp_path / "jobs")


@pytest.fixture
def sample_config() -> RenderJobConfig:
    """Sample render job config."""
    return RenderJobConfig(
        session_id="test-session-1",
        layout="default-1920x1080",
        output_file="/tmp/output1.mp4",
    )


@pytest.fixture
def sample_config_2() -> RenderJobConfig:
    """Second sample render job config."""
    return RenderJobConfig(
        session_id="test-session-2",
        layout="default-1920x1080",
        output_file="/tmp/output2.mp4",
    )


@pytest.fixture
def sample_config_3() -> RenderJobConfig:
    """Third sample render job config."""
    return RenderJobConfig(
        session_id="test-session-3",
        layout="default-1920x1080",
        output_file="/tmp/output3.mp4",
    )


class TestJobCreation:
    """Test basic job creation."""

    @pytest.mark.asyncio
    async def test_create_job(self, job_manager_instance: JobManager, sample_config: RenderJobConfig):
        """Test creating a single job."""
        job = await job_manager_instance.create_job(sample_config)

        assert job.id is not None
        assert job.status == JobStatus.PENDING
        assert job.config.session_id == sample_config.session_id
        assert job.batch_id is None

    @pytest.mark.asyncio
    async def test_create_job_persists_to_disk(self, job_manager_instance: JobManager, sample_config: RenderJobConfig):
        """Test that created job is persisted to disk."""
        job = await job_manager_instance.create_job(sample_config)

        job_file = job_manager_instance.state_dir / f"{job.id}.json"
        assert job_file.exists()


class TestBatchJobCreation:
    """Test batch job creation and management."""

    @pytest.mark.asyncio
    async def test_create_job_with_batch(self, job_manager_instance: JobManager, sample_config: RenderJobConfig):
        """Test creating a job with batch ID."""
        batch_id = "test-batch-123"
        job = await job_manager_instance.create_job_with_batch(sample_config, batch_id=batch_id)

        assert job.batch_id == batch_id
        assert job.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_multiple_batch_jobs(
        self,
        job_manager_instance: JobManager,
        sample_config: RenderJobConfig,
        sample_config_2: RenderJobConfig,
        sample_config_3: RenderJobConfig,
    ):
        """Test creating multiple jobs in a batch."""
        batch_id = "test-batch-456"

        job1 = await job_manager_instance.create_job_with_batch(sample_config, batch_id=batch_id)
        job2 = await job_manager_instance.create_job_with_batch(sample_config_2, batch_id=batch_id)
        job3 = await job_manager_instance.create_job_with_batch(sample_config_3, batch_id=batch_id)

        assert job1.batch_id == batch_id
        assert job2.batch_id == batch_id
        assert job3.batch_id == batch_id

        # All jobs should be pending
        assert job1.status == JobStatus.PENDING
        assert job2.status == JobStatus.PENDING
        assert job3.status == JobStatus.PENDING


class TestBatchJobCounting:
    """Test batch job counting functionality."""

    @pytest.mark.asyncio
    async def test_count_batch_jobs_empty(self, job_manager_instance: JobManager):
        """Test counting jobs for non-existent batch."""
        counts = await job_manager_instance.count_batch_jobs("non-existent-batch")

        assert counts["total"] == 0
        assert counts["pending"] == 0
        assert counts["running"] == 0
        assert counts["completed"] == 0
        assert counts["failed"] == 0
        assert counts["cancelled"] == 0

    @pytest.mark.asyncio
    async def test_count_batch_jobs(
        self,
        job_manager_instance: JobManager,
        sample_config: RenderJobConfig,
        sample_config_2: RenderJobConfig,
        sample_config_3: RenderJobConfig,
    ):
        """Test counting jobs in a batch."""
        batch_id = "test-batch-789"

        await job_manager_instance.create_job_with_batch(sample_config, batch_id=batch_id)
        await job_manager_instance.create_job_with_batch(sample_config_2, batch_id=batch_id)
        await job_manager_instance.create_job_with_batch(sample_config_3, batch_id=batch_id)

        counts = await job_manager_instance.count_batch_jobs(batch_id)

        assert counts["total"] == 3
        assert counts["pending"] == 3
        assert counts["running"] == 0
        assert counts["completed"] == 0
        assert counts["failed"] == 0
        assert counts["cancelled"] == 0

    @pytest.mark.asyncio
    async def test_count_batch_jobs_with_different_statuses(
        self,
        job_manager_instance: JobManager,
        sample_config: RenderJobConfig,
        sample_config_2: RenderJobConfig,
        sample_config_3: RenderJobConfig,
    ):
        """Test counting jobs with different statuses."""
        batch_id = "test-batch-mixed"

        job1 = await job_manager_instance.create_job_with_batch(sample_config, batch_id=batch_id)
        job2 = await job_manager_instance.create_job_with_batch(sample_config_2, batch_id=batch_id)
        await job_manager_instance.create_job_with_batch(sample_config_3, batch_id=batch_id)  # job3 stays PENDING

        # Update statuses
        await job_manager_instance.update_job_status(job1.id, JobStatus.COMPLETED)
        await job_manager_instance.update_job_status(job2.id, JobStatus.RUNNING)

        counts = await job_manager_instance.count_batch_jobs(batch_id)

        assert counts["total"] == 3
        assert counts["pending"] == 1
        assert counts["running"] == 1
        assert counts["completed"] == 1
        assert counts["failed"] == 0
        assert counts["cancelled"] == 0


class TestBatchJobCancellation:
    """Test batch job cancellation functionality."""

    @pytest.mark.asyncio
    async def test_cancel_batch_pending_jobs(
        self,
        job_manager_instance: JobManager,
        sample_config: RenderJobConfig,
        sample_config_2: RenderJobConfig,
        sample_config_3: RenderJobConfig,
    ):
        """Test cancelling all pending jobs in a batch."""
        batch_id = "test-batch-cancel"

        job1 = await job_manager_instance.create_job_with_batch(sample_config, batch_id=batch_id)
        job2 = await job_manager_instance.create_job_with_batch(sample_config_2, batch_id=batch_id)
        job3 = await job_manager_instance.create_job_with_batch(sample_config_3, batch_id=batch_id)

        # Make one job running (shouldn't be cancelled by this method)
        await job_manager_instance.update_job_status(job1.id, JobStatus.RUNNING)

        cancelled_count = await job_manager_instance.cancel_batch_pending_jobs(batch_id)

        assert cancelled_count == 2  # Only pending jobs

        # Verify statuses
        job1_updated = await job_manager_instance.get_job(job1.id)
        job2_updated = await job_manager_instance.get_job(job2.id)
        job3_updated = await job_manager_instance.get_job(job3.id)

        assert job1_updated.status == JobStatus.RUNNING  # Not cancelled
        assert job2_updated.status == JobStatus.CANCELLED
        assert job3_updated.status == JobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_batch_pending_jobs_none_pending(
        self,
        job_manager_instance: JobManager,
        sample_config: RenderJobConfig,
    ):
        """Test cancelling when no pending jobs exist."""
        batch_id = "test-batch-no-pending"

        job = await job_manager_instance.create_job_with_batch(sample_config, batch_id=batch_id)
        await job_manager_instance.update_job_status(job.id, JobStatus.COMPLETED)

        cancelled_count = await job_manager_instance.cancel_batch_pending_jobs(batch_id)

        assert cancelled_count == 0


class TestGetRunningBatchJob:
    """Test getting running job from a batch."""

    @pytest.mark.asyncio
    async def test_get_running_batch_job_none(
        self,
        job_manager_instance: JobManager,
        sample_config: RenderJobConfig,
    ):
        """Test getting running job when none is running."""
        batch_id = "test-batch-no-running"

        await job_manager_instance.create_job_with_batch(sample_config, batch_id=batch_id)

        running_job = await job_manager_instance.get_running_batch_job(batch_id)

        assert running_job is None

    @pytest.mark.asyncio
    async def test_get_running_batch_job(
        self,
        job_manager_instance: JobManager,
        sample_config: RenderJobConfig,
        sample_config_2: RenderJobConfig,
    ):
        """Test getting running job from batch."""
        batch_id = "test-batch-with-running"

        job1 = await job_manager_instance.create_job_with_batch(sample_config, batch_id=batch_id)
        await job_manager_instance.create_job_with_batch(sample_config_2, batch_id=batch_id)  # job2 pending

        await job_manager_instance.update_job_status(job1.id, JobStatus.RUNNING)

        running_job = await job_manager_instance.get_running_batch_job(batch_id)

        assert running_job is not None
        assert running_job.id == job1.id


class TestGetNextPendingJob:
    """Test getting next pending job (FIFO order)."""

    @pytest.mark.asyncio
    async def test_get_next_pending_job_fifo_order(
        self,
        job_manager_instance: JobManager,
        sample_config: RenderJobConfig,
        sample_config_2: RenderJobConfig,
        sample_config_3: RenderJobConfig,
    ):
        """Test that next pending job is returned in FIFO order."""
        job1 = await job_manager_instance.create_job(sample_config)
        job2 = await job_manager_instance.create_job(sample_config_2)
        await job_manager_instance.create_job(sample_config_3)  # job3 in queue

        next_job = await job_manager_instance.get_next_pending_job()

        # Should return the first created job
        assert next_job.id == job1.id

        # Complete first job and check next
        await job_manager_instance.update_job_status(job1.id, JobStatus.COMPLETED)
        next_job = await job_manager_instance.get_next_pending_job()

        assert next_job.id == job2.id

    @pytest.mark.asyncio
    async def test_get_next_pending_job_empty(self, job_manager_instance: JobManager):
        """Test getting next pending job when queue is empty."""
        next_job = await job_manager_instance.get_next_pending_job()

        assert next_job is None


class TestJobStatusUpdates:
    """Test job status update functionality."""

    @pytest.mark.asyncio
    async def test_update_job_to_running(self, job_manager_instance: JobManager, sample_config: RenderJobConfig):
        """Test updating job status to running."""
        job = await job_manager_instance.create_job(sample_config)

        await job_manager_instance.update_job_status(job.id, JobStatus.RUNNING)

        updated_job = await job_manager_instance.get_job(job.id)
        assert updated_job.status == JobStatus.RUNNING
        assert updated_job.started_at is not None

    @pytest.mark.asyncio
    async def test_update_job_to_completed(self, job_manager_instance: JobManager, sample_config: RenderJobConfig):
        """Test updating job status to completed."""
        job = await job_manager_instance.create_job(sample_config)
        await job_manager_instance.update_job_status(job.id, JobStatus.RUNNING)

        await job_manager_instance.update_job_status(job.id, JobStatus.COMPLETED)

        updated_job = await job_manager_instance.get_job(job.id)
        assert updated_job.status == JobStatus.COMPLETED
        assert updated_job.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_job_to_failed_with_error(
        self, job_manager_instance: JobManager, sample_config: RenderJobConfig
    ):
        """Test updating job status to failed with error message."""
        job = await job_manager_instance.create_job(sample_config)

        await job_manager_instance.update_job_status(job.id, JobStatus.FAILED, error="Test error message")

        updated_job = await job_manager_instance.get_job(job.id)
        assert updated_job.status == JobStatus.FAILED
        assert updated_job.error == "Test error message"
        assert updated_job.completed_at is not None


class TestJobProgress:
    """Test job progress update functionality."""

    @pytest.mark.asyncio
    async def test_update_job_progress(self, job_manager_instance: JobManager, sample_config: RenderJobConfig):
        """Test updating job progress."""
        job = await job_manager_instance.create_job(sample_config)
        await job_manager_instance.update_job_status(job.id, JobStatus.RUNNING)

        await job_manager_instance.update_job_progress(
            job.id,
            percent=50.0,
            current_frame=500,
            total_frames=1000,
            fps=25.5,
            eta_seconds=20.0,
        )

        updated_job = await job_manager_instance.get_job(job.id)
        assert updated_job.progress.percent == 50.0
        assert updated_job.progress.current_frame == 500
        assert updated_job.progress.total_frames == 1000
        assert updated_job.progress.fps == 25.5
        assert updated_job.progress.eta_seconds == 20.0

    @pytest.mark.asyncio
    async def test_progress_percent_capped_at_100(
        self, job_manager_instance: JobManager, sample_config: RenderJobConfig
    ):
        """Test that progress percent is capped at 100."""
        job = await job_manager_instance.create_job(sample_config)

        await job_manager_instance.update_job_progress(job.id, percent=150.0)

        updated_job = await job_manager_instance.get_job(job.id)
        assert updated_job.progress.percent == 100.0
