"""Job management service for background render tasks."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from gpstitch.config import settings
from gpstitch.models.job import Job, JobStatus, JobType, RenderJobConfig

logger = logging.getLogger(__name__)


class JobManager:
    """Manages background jobs with persistence and recovery."""

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or (settings.temp_dir / "jobs")
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # In-memory job registry
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

        # Current running job (only one at a time)
        self._current_job_id: str | None = None

        # Load persisted jobs on startup
        self._load_jobs()

    def _job_file_path(self, job_id: str) -> Path:
        """Get path to job state file."""
        return self.state_dir / f"{job_id}.json"

    def _load_jobs(self):
        """Load persisted jobs from disk."""
        for job_file in self.state_dir.glob("*.json"):
            try:
                job_data = json.loads(job_file.read_text())
                job = Job.model_validate(job_data)
                self._jobs[job.id] = job

                # Mark previously running jobs as failed (server restart)
                if job.status == JobStatus.RUNNING:
                    job.status = JobStatus.FAILED
                    job.error = "Server restarted during execution"
                    job.completed_at = datetime.now(UTC)
                    self._persist_job(job)
                    logger.warning(f"Marked job {job.id} as failed due to server restart")

                # Mark pending jobs with local sessions as failed (local sessions are in-memory only)
                elif job.status == JobStatus.PENDING and job.config.session_id.startswith("local:"):
                    job.status = JobStatus.FAILED
                    job.error = "Server restarted - local session lost"
                    job.completed_at = datetime.now(UTC)
                    self._persist_job(job)
                    logger.warning(f"Marked job {job.id} as failed - local session lost on restart")

            except Exception as e:
                logger.error(f"Failed to load job from {job_file}: {e}")

    def _persist_job(self, job: Job):
        """Persist job state to disk."""
        job_file = self._job_file_path(job.id)
        job_file.write_text(job.model_dump_json(indent=2))

    async def create_job(self, config: RenderJobConfig) -> Job:
        """Create a new render job."""
        async with self._lock:
            job = Job(
                id=str(uuid4()),
                type=JobType.RENDER,
                status=JobStatus.PENDING,
                config=config,
                created_at=datetime.now(UTC),
            )

            self._jobs[job.id] = job
            self._persist_job(job)

            logger.info(f"Created job {job.id} for session {config.session_id}")
            return job

    async def get_job(self, job_id: str) -> Job | None:
        """Get job by ID."""
        return self._jobs.get(job_id)

    async def list_jobs(self, limit: int = 50) -> list[Job]:
        """List recent jobs, newest first."""
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    async def get_current_job(self) -> Job | None:
        """Get the currently running job."""
        if self._current_job_id:
            return self._jobs.get(self._current_job_id)
        return None

    async def has_active_job(self) -> bool:
        """Check if there's an active job running."""
        return self._current_job_id is not None

    async def update_job_status(self, job_id: str, status: JobStatus, error: str | None = None):
        """Update job status."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            job.status = status
            if error:
                job.error = error

            if status == JobStatus.RUNNING:
                job.started_at = datetime.now(UTC)
                self._current_job_id = job_id
            elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                job.completed_at = datetime.now(UTC)
                if self._current_job_id == job_id:
                    self._current_job_id = None

            self._persist_job(job)
            logger.info(f"Job {job_id} status updated to {status}")

    async def update_job_progress(
        self,
        job_id: str,
        percent: float,
        current_frame: int | None = None,
        total_frames: int | None = None,
        fps: float | None = None,
        eta_seconds: float | None = None,
    ):
        """Update job progress."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            job.progress.percent = min(percent, 100.0)
            if current_frame is not None:
                job.progress.current_frame = current_frame
            if total_frames is not None:
                job.progress.total_frames = total_frames
            if fps is not None:
                job.progress.fps = fps
            if eta_seconds is not None:
                job.progress.eta_seconds = eta_seconds

            # Persist periodically (every 5% or every 100 frames)
            should_persist = int(percent) % 5 == 0 or (current_frame and current_frame % 100 == 0)
            if should_persist:
                self._persist_job(job)

    async def append_job_log(self, job_id: str, line: str):
        """Append a line to job log."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            # Keep last 500 lines to prevent memory issues
            job.log_lines.append(line)
            if len(job.log_lines) > 500:
                job.log_lines = job.log_lines[-500:]

    async def set_job_pid(self, job_id: str, pid: int):
        """Set the process ID for a running job."""
        job = self._jobs.get(job_id)
        if job:
            job.pid = pid
            self._persist_job(job)

    async def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Remove old completed/failed jobs."""
        async with self._lock:
            now = datetime.now(UTC)
            to_remove = []

            for job_id, job in self._jobs.items():
                if job.is_terminal() and job.completed_at:
                    age_hours = (now - job.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(job_id)

            for job_id in to_remove:
                del self._jobs[job_id]
                job_file = self._job_file_path(job_id)
                if job_file.exists():
                    job_file.unlink()
                logger.info(f"Cleaned up old job {job_id}")

            return len(to_remove)

    async def get_next_pending_job(self) -> Job | None:
        """Get the next pending job from queue (FIFO by created_at)."""
        pending = [j for j in self._jobs.values() if j.status == JobStatus.PENDING]
        if pending:
            return sorted(pending, key=lambda j: j.created_at)[0]
        return None

    async def has_pending_jobs(self) -> bool:
        """Check if there are pending jobs in queue."""
        return any(j.status == JobStatus.PENDING for j in self._jobs.values())

    async def count_batch_jobs(self, batch_id: str) -> dict:
        """Count jobs in a batch by status."""
        jobs = [j for j in self._jobs.values() if j.batch_id == batch_id]
        return {
            "total": len(jobs),
            "pending": sum(1 for j in jobs if j.status == JobStatus.PENDING),
            "running": sum(1 for j in jobs if j.status == JobStatus.RUNNING),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
            "cancelled": sum(1 for j in jobs if j.status == JobStatus.CANCELLED),
        }

    async def create_job_with_batch(self, config: RenderJobConfig, batch_id: str | None = None) -> Job:
        """Create a new render job with optional batch ID."""
        async with self._lock:
            job = Job(
                id=str(uuid4()),
                type=JobType.RENDER,
                status=JobStatus.PENDING,
                config=config,
                created_at=datetime.now(UTC),
                batch_id=batch_id,
            )

            self._jobs[job.id] = job
            self._persist_job(job)

            logger.info(
                f"Created job {job.id} for session {config.session_id}" + (f" (batch {batch_id})" if batch_id else "")
            )
            return job

    async def cancel_batch_pending_jobs(self, batch_id: str) -> int:
        """Cancel all pending jobs in a batch. Returns count of cancelled jobs."""
        cancelled = 0
        async with self._lock:
            for job in self._jobs.values():
                if job.batch_id == batch_id and job.status == JobStatus.PENDING:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.now(UTC)
                    self._persist_job(job)
                    cancelled += 1
                    logger.info(f"Cancelled pending job {job.id} from batch {batch_id}")
        return cancelled

    async def get_running_batch_job(self, batch_id: str) -> Job | None:
        """Get the running job in a batch, if any."""
        for job in self._jobs.values():
            if job.batch_id == batch_id and job.status == JobStatus.RUNNING:
                return job
        return None

    async def cleanup_orphaned_pending_jobs(self, valid_session_ids: set) -> int:
        """Mark pending jobs as failed if their session no longer exists.

        Args:
            valid_session_ids: Set of session IDs that currently exist

        Returns:
            Number of jobs marked as failed
        """
        cleaned = 0
        async with self._lock:
            for job in self._jobs.values():
                if job.status == JobStatus.PENDING and job.config.session_id not in valid_session_ids:
                    job.status = JobStatus.FAILED
                    job.error = "Session no longer exists (orphaned job)"
                    job.completed_at = datetime.now(UTC)
                    self._persist_job(job)
                    cleaned += 1
                    logger.info(f"Cleaned up orphaned job {job.id} (session {job.config.session_id})")
        return cleaned


# Global job manager instance
job_manager = JobManager()
