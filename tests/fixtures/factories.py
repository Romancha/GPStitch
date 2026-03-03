"""Factory functions for creating test models."""

from datetime import UTC, datetime
from uuid import uuid4

from gpstitch.models.editor import (
    CanvasSettings,
    EditorLayout,
    LayoutMetadata,
    WidgetInstance,
)
from gpstitch.models.job import Job, JobProgress, JobStatus, JobType, RenderJobConfig
from gpstitch.models.schemas import FileInfo, FileRole, GpxFitMetadata, VideoMetadata


def create_video_metadata(
    width: int = 1920,
    height: int = 1080,
    duration_seconds: float = 60.0,
    frame_count: int = 1800,
    frame_rate: float = 30.0,
    has_gps: bool = True,
) -> VideoMetadata:
    """Create VideoMetadata with defaults."""
    return VideoMetadata(
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        frame_count=frame_count,
        frame_rate=frame_rate,
        has_gps=has_gps,
    )


def create_gpx_fit_metadata(
    gps_point_count: int = 500,
    duration_seconds: float | None = 60.0,
) -> GpxFitMetadata:
    """Create GpxFitMetadata with defaults."""
    return GpxFitMetadata(
        gps_point_count=gps_point_count,
        duration_seconds=duration_seconds,
    )


def create_file_info(
    filename: str = "test.mp4",
    file_path: str = "/tmp/test.mp4",
    file_type: str = "video",
    role: FileRole = FileRole.PRIMARY,
    video_metadata: VideoMetadata | None = None,
    gpx_fit_metadata: GpxFitMetadata | None = None,
) -> FileInfo:
    """Create FileInfo with defaults."""
    return FileInfo(
        filename=filename,
        file_path=file_path,
        file_type=file_type,
        role=role,
        video_metadata=video_metadata,
        gpx_fit_metadata=gpx_fit_metadata,
    )


def create_render_config(
    session_id: str | None = None,
    layout: str = "default-1920x1080",
    layout_xml_path: str | None = None,
    output_file: str = "/tmp/output.mp4",
    units_speed: str = "kph",
    units_altitude: str = "metre",
    units_distance: str = "km",
    units_temperature: str = "degC",
    map_style: str | None = None,
    gpx_merge_mode: str = "OVERWRITE",
    video_time_alignment: str | None = None,
    ffmpeg_profile: str | None = None,
) -> RenderJobConfig:
    """Create RenderJobConfig with defaults."""
    return RenderJobConfig(
        session_id=session_id or f"test-session-{uuid4().hex[:8]}",
        layout=layout,
        layout_xml_path=layout_xml_path,
        output_file=output_file,
        units_speed=units_speed,
        units_altitude=units_altitude,
        units_distance=units_distance,
        units_temperature=units_temperature,
        map_style=map_style,
        gpx_merge_mode=gpx_merge_mode,
        video_time_alignment=video_time_alignment,
        ffmpeg_profile=ffmpeg_profile,
    )


def create_job(
    job_id: str | None = None,
    config: RenderJobConfig | None = None,
    status: JobStatus = JobStatus.PENDING,
    batch_id: str | None = None,
) -> Job:
    """Create Job with defaults."""
    return Job(
        id=job_id or str(uuid4()),
        type=JobType.RENDER,
        status=status,
        config=config or create_render_config(),
        created_at=datetime.now(UTC),
        progress=JobProgress(),
        batch_id=batch_id,
    )


def create_widget_instance(
    widget_id: str | None = None,
    widget_type: str = "text",
    name: str | None = None,
    x: int = 0,
    y: int = 0,
    properties: dict | None = None,
    children: list | None = None,
) -> WidgetInstance:
    """Create WidgetInstance with defaults."""
    default_props = {
        "text": {"value": "Text", "size": 32, "rgb": "255,255,255"},
        "metric": {"metric": "speed", "units": "kph", "dp": 1},
        "moving_map": {"size": 256, "zoom": 16},
    }
    return WidgetInstance(
        id=widget_id or str(uuid4()),
        type=widget_type,
        name=name,
        x=x,
        y=y,
        properties=properties or default_props.get(widget_type, {}),
        children=children or [],
    )


def create_editor_layout(
    layout_id: str | None = None,
    name: str = "Test Layout",
    description: str | None = None,
    width: int = 1920,
    height: int = 1080,
    widgets: list[WidgetInstance] | None = None,
) -> EditorLayout:
    """Create EditorLayout with defaults."""
    if widgets is None:
        widgets = [
            create_widget_instance(widget_type="text", x=100, y=50),
            create_widget_instance(widget_type="metric", x=100, y=100),
        ]
    return EditorLayout(
        id=layout_id or str(uuid4()),
        metadata=LayoutMetadata(name=name, description=description),
        canvas=CanvasSettings(width=width, height=height),
        widgets=widgets,
    )
