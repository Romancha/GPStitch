"""Job domain models for render tasks."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from gpstitch.constants import (
    DEFAULT_GPS_DOP_MAX,
    DEFAULT_GPS_SPEED_MAX,
    DEFAULT_GPX_MERGE_MODE,
    DEFAULT_UNITS_ALTITUDE,
    DEFAULT_UNITS_DISTANCE,
    DEFAULT_UNITS_SPEED,
    DEFAULT_UNITS_TEMPERATURE,
)


class JobStatus(str, Enum):
    """Job execution status."""

    PENDING = "pending"  # Queued, not started
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Failed with error
    CANCELLED = "cancelled"  # User cancelled


class JobType(str, Enum):
    """Type of job."""

    RENDER = "render"


class RenderJobConfig(BaseModel):
    """Configuration for a render job."""

    session_id: str
    layout: str
    layout_xml_path: str | None = None
    output_file: str
    units_speed: str = DEFAULT_UNITS_SPEED
    units_altitude: str = DEFAULT_UNITS_ALTITUDE
    units_distance: str = DEFAULT_UNITS_DISTANCE
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE
    map_style: str | None = None
    gpx_merge_mode: str = DEFAULT_GPX_MERGE_MODE
    video_time_alignment: str | None = None
    ffmpeg_profile: str | None = None  # FFmpeg encoding profile name
    gps_dop_max: float = DEFAULT_GPS_DOP_MAX
    gps_speed_max: float = DEFAULT_GPS_SPEED_MAX


class JobProgress(BaseModel):
    """Progress information for a job."""

    percent: float = Field(default=0, ge=0, le=100)
    current_frame: int | None = None
    total_frames: int | None = None
    fps: float | None = None
    eta_seconds: float | None = None


class Job(BaseModel):
    """Represents a render job."""

    id: str
    type: JobType = JobType.RENDER
    status: JobStatus = JobStatus.PENDING
    config: RenderJobConfig
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: JobProgress = Field(default_factory=JobProgress)
    log_lines: list[str] = Field(default_factory=list)
    error: str | None = None
    pid: int | None = None
    batch_id: str | None = None  # Groups jobs from same batch

    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)

    def is_running(self) -> bool:
        """Check if job is currently running."""
        return self.status == JobStatus.RUNNING
