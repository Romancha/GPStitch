"""Upload API endpoint."""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from gpstitch.config import settings
from gpstitch.models.schemas import (
    ConfigResponse,
    FileRole,
    LocalFileRequest,
    SecondaryFileRequest,
    UploadResponse,
)
from gpstitch.services.file_manager import file_manager
from gpstitch.services.gps_analyzer import analyze_external_gps_quality, analyze_gps_quality
from gpstitch.services.metadata import (
    extract_gpx_fit_metadata,
    extract_video_metadata,
    get_file_type,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Get application configuration."""
    return ConfigResponse(
        local_mode=settings.local_mode,
        max_upload_size_bytes=settings.max_upload_size_bytes,
        allowed_extensions=list(settings.allowed_extensions),
    )


@router.post("/local-file", response_model=UploadResponse)
async def use_local_file(request: LocalFileRequest) -> UploadResponse:
    """Use a local file path instead of uploading.

    Only available when GPSTITCH_LOCAL_MODE=true.
    """
    if not settings.local_mode:
        raise HTTPException(
            status_code=403,
            detail="Local file mode is disabled. Set GPSTITCH_LOCAL_MODE=true to enable.",
        )

    file_path = Path(request.file_path).expanduser().resolve()

    # Validate file exists
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {file_path}")

    # Validate extension
    extension = file_path.suffix.lower()
    if extension not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(settings.allowed_extensions)}",
        )

    # Determine file type and extract metadata
    file_type = get_file_type(file_path)

    # Check if we should reuse an existing session with GPX/FIT primary
    reuse_session = False
    session_id = request.session_id
    if session_id and file_manager.session_exists(session_id):
        existing_primary = file_manager.get_primary_file(session_id)
        if existing_primary and existing_primary.file_type in ("gpx", "fit", "srt") and file_type == "video":
            reuse_session = True

    if not reuse_session:
        session_id = file_manager.create_local_session()

    video_metadata = None
    gpx_fit_metadata = None
    gps_quality = None

    if file_type == "video":
        try:
            video_metadata = extract_video_metadata(file_path)
        except Exception as e:
            logger.error(f"Failed to extract video metadata: {e}")
            if not reuse_session:
                file_manager.cleanup_session(session_id)
            raise HTTPException(
                status_code=400,
                detail="Could not read video file. Ensure it's a valid video format.",
            ) from e

        # Analyze GPS quality if video has GPS data
        if video_metadata and video_metadata.has_gps:
            try:
                gps_quality = analyze_gps_quality(file_path)
            except Exception as e:
                logger.warning(f"Failed to analyze GPS quality: {e}")
                # Don't fail the upload, just skip GPS quality analysis

    elif file_type in ("gpx", "fit", "srt"):
        try:
            gpx_fit_metadata = extract_gpx_fit_metadata(file_path)
        except Exception as e:
            logger.error(f"Failed to extract GPX/FIT metadata: {e}")
            if not reuse_session:
                file_manager.cleanup_session(session_id)
            raise HTTPException(
                status_code=400,
                detail=f"Could not read {file_type.upper()} file. Ensure it's a valid format.",
            ) from e

        # Analyze GPS quality for external telemetry file
        try:
            gps_quality = analyze_external_gps_quality(file_path)
        except Exception as e:
            logger.warning(f"Failed to analyze GPS quality: {e}")

    # If reusing session, promote video to primary (demote GPX/FIT to secondary)
    if reuse_session:
        try:
            files = file_manager.promote_to_primary(
                session_id=session_id,
                filename=file_path.name,
                file_path=file_path,
                file_type=file_type,
                video_metadata=video_metadata,
                gps_quality=gps_quality,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        return UploadResponse(
            session_id=session_id,
            files=files,
        )

    # Add file to session as primary
    file_info = file_manager.add_file(
        session_id=session_id,
        filename=file_path.name,
        file_path=file_path,
        file_type=file_type,
        role=FileRole.PRIMARY,
        video_metadata=video_metadata,
        gpx_fit_metadata=gpx_fit_metadata,
        gps_quality=gps_quality,
    )

    # Auto-detect matching SRT/GPX/FIT file for video (e.g. DJI_0001.MP4 → DJI_0001.SRT)
    # Skip auto-detection if video has embedded DJI meta GPS (self-contained)
    files = [file_info]
    has_embedded_gps = video_metadata and video_metadata.has_dji_meta
    if file_type == "video" and settings.local_mode and not has_embedded_gps:
        auto_secondary = _find_matching_telemetry(file_path)
        if auto_secondary:
            try:
                secondary_metadata = extract_gpx_fit_metadata(auto_secondary)
                secondary_type = get_file_type(auto_secondary)
                secondary_quality = None
                try:
                    secondary_quality = analyze_external_gps_quality(auto_secondary)
                except Exception as e:
                    logger.warning(f"Failed to analyze GPS quality for auto-detected file: {e}")
                secondary_info = file_manager.add_file(
                    session_id=session_id,
                    filename=auto_secondary.name,
                    file_path=auto_secondary,
                    file_type=secondary_type,
                    role=FileRole.SECONDARY,
                    gpx_fit_metadata=secondary_metadata,
                    gps_quality=secondary_quality,
                )
                files.append(secondary_info)
                logger.info(f"Auto-detected telemetry file: {auto_secondary.name}")
            except Exception as e:
                logger.warning(f"Failed to auto-load telemetry file {auto_secondary}: {e}")

    return UploadResponse(
        session_id=session_id,
        files=files,
    )


def _find_matching_telemetry(video_path: Path) -> Path | None:
    """Find a matching telemetry file (SRT, GPX, FIT) next to the video.

    DJI drones create files like:
        DJI_20240807123424_0002_D.MP4
        DJI_20240807123424_0002_D.SRT

    Checks for .srt first (DJI), then .gpx, then .fit.
    """
    for ext in (".srt", ".gpx", ".fit"):
        candidate = video_path.with_suffix(ext)
        if candidate.exists():
            return candidate
        # Also try uppercase extension
        candidate = video_path.with_suffix(ext.upper())
        if candidate.exists():
            return candidate
    return None


@router.post("/local-file-secondary", response_model=UploadResponse)
async def use_local_secondary_file(request: SecondaryFileRequest) -> UploadResponse:
    """Add a secondary GPX/FIT file from local path.

    Only available when GPSTITCH_LOCAL_MODE=true.
    """
    if not settings.local_mode:
        raise HTTPException(
            status_code=403,
            detail="Local file mode is disabled. Set GPSTITCH_LOCAL_MODE=true to enable.",
        )

    # Validate session exists
    if not file_manager.session_exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    file_path = Path(request.file_path).expanduser().resolve()

    # Validate file exists
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {file_path}")

    # Validate extension - only GPX/FIT allowed for secondary
    extension = file_path.suffix.lower()
    if extension not in (".gpx", ".fit", ".srt"):
        raise HTTPException(
            status_code=400,
            detail="Secondary file must be GPX, FIT, or SRT",
        )

    # Determine file type and extract metadata
    file_type = get_file_type(file_path)
    gpx_fit_metadata = None

    try:
        gpx_fit_metadata = extract_gpx_fit_metadata(file_path)
    except Exception as e:
        logger.error(f"Failed to extract GPX/FIT metadata: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Could not read {file_type.upper()} file. Ensure it's a valid format.",
        ) from e

    # Analyze GPS quality for external telemetry file
    gps_quality = None
    try:
        gps_quality = analyze_external_gps_quality(file_path)
    except Exception as e:
        logger.warning(f"Failed to analyze GPS quality for secondary file: {e}")

    # Add file to session as secondary
    try:
        file_manager.add_file(
            session_id=request.session_id,
            filename=file_path.name,
            file_path=file_path,
            file_type=file_type,
            role=FileRole.SECONDARY,
            gpx_fit_metadata=gpx_fit_metadata,
            gps_quality=gps_quality,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Return all files
    files = file_manager.get_files(request.session_id)

    return UploadResponse(
        session_id=request.session_id,
        files=files,
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: Annotated[UploadFile, File(...)],
    session_id: Annotated[str | None, Form()] = None,
) -> UploadResponse:
    """Upload a GoPro MP4, GPX, or FIT file as primary.

    If session_id is provided and the session has a GPX/FIT as primary,
    the video will be promoted to primary and the GPX/FIT demoted to secondary.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate file extension
    extension = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(settings.allowed_extensions)}",
        )

    # Read file content
    content = await file.read()

    # Check file size
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.max_upload_size_bytes / (1024 * 1024 * 1024):.1f}GB",
        )

    # Check if we should reuse an existing session with GPX/FIT primary
    reuse_session = False
    if session_id and file_manager.session_exists(session_id):
        existing_primary = file_manager.get_primary_file(session_id)
        file_type_preview = get_file_type(Path(file.filename))
        if existing_primary and existing_primary.file_type in ("gpx", "fit", "srt") and file_type_preview == "video":
            reuse_session = True

    if reuse_session:
        # Save video to existing session
        file_path = file_manager.save_file(session_id, file.filename, content)
    else:
        # Create new session
        session_id = file_manager.create_session()
        file_path = file_manager.save_file(session_id, file.filename, content)

    # Determine file type
    file_type = get_file_type(file_path)

    # Extract metadata based on file type
    video_metadata = None
    gpx_fit_metadata = None
    gps_quality = None

    if file_type == "video":
        try:
            video_metadata = extract_video_metadata(file_path)
        except Exception as e:
            logger.error(f"Failed to extract video metadata: {e}")
            if not reuse_session:
                file_manager.cleanup_session(session_id)
            else:
                file_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail="Could not read video file. Ensure it's a valid video format.",
            ) from e

        # Analyze GPS quality if video has GPS data
        if video_metadata and video_metadata.has_gps:
            try:
                gps_quality = analyze_gps_quality(file_path)
            except Exception as e:
                logger.warning(f"Failed to analyze GPS quality: {e}")
                # Don't fail the upload, just skip GPS quality analysis

    elif file_type in ("gpx", "fit", "srt"):
        try:
            gpx_fit_metadata = extract_gpx_fit_metadata(file_path)
        except Exception as e:
            logger.error(f"Failed to extract GPX/FIT metadata: {e}")
            if not reuse_session:
                file_manager.cleanup_session(session_id)
            else:
                file_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=f"Could not read {file_type.upper()} file. Ensure it's a valid format.",
            ) from e

        # Analyze GPS quality for external telemetry file
        try:
            gps_quality = analyze_external_gps_quality(file_path)
        except Exception as e:
            logger.warning(f"Failed to analyze GPS quality: {e}")

    # If reusing session, promote video to primary (demote GPX/FIT to secondary)
    if reuse_session:
        try:
            files = file_manager.promote_to_primary(
                session_id=session_id,
                filename=file.filename,
                file_path=file_path,
                file_type=file_type,
                video_metadata=video_metadata,
                gps_quality=gps_quality,
            )
        except ValueError as e:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(e)) from e

        return UploadResponse(
            session_id=session_id,
            files=files,
        )

    # Add file to session as primary
    file_info = file_manager.add_file(
        session_id=session_id,
        filename=file.filename,
        file_path=file_path,
        file_type=file_type,
        role=FileRole.PRIMARY,
        video_metadata=video_metadata,
        gpx_fit_metadata=gpx_fit_metadata,
        gps_quality=gps_quality,
    )

    return UploadResponse(
        session_id=session_id,
        files=[file_info],
    )


@router.post("/upload-secondary", response_model=UploadResponse)
async def upload_secondary_file(
    session_id: Annotated[str, Form(...)],
    file: Annotated[UploadFile, File(...)],
) -> UploadResponse:
    """Upload a secondary GPX/FIT file to existing session."""
    # Validate session exists
    if not file_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate file extension - only GPX/FIT allowed
    extension = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension not in (".gpx", ".fit", ".srt"):
        raise HTTPException(
            status_code=400,
            detail="Secondary file must be GPX, FIT, or SRT",
        )

    # Read file content
    content = await file.read()

    # Check file size (GPX/FIT are typically small)
    max_secondary_size = 50 * 1024 * 1024  # 50MB
    if len(content) > max_secondary_size:
        raise HTTPException(
            status_code=413,
            detail=f"Secondary file too large. Maximum size: {max_secondary_size / (1024 * 1024):.0f}MB",
        )

    # Save file to session
    file_path = file_manager.save_file(session_id, file.filename, content)

    # Determine file type and extract metadata
    file_type = get_file_type(file_path)
    gpx_fit_metadata = None

    try:
        gpx_fit_metadata = extract_gpx_fit_metadata(file_path)
    except Exception as e:
        logger.error(f"Failed to extract GPX/FIT metadata: {e}")
        # Remove the file
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Could not read {file_type.upper()} file. Ensure it's a valid format.",
        ) from e

    # Analyze GPS quality for external telemetry file
    gps_quality = None
    try:
        gps_quality = analyze_external_gps_quality(file_path)
    except Exception as e:
        logger.warning(f"Failed to analyze GPS quality for secondary file: {e}")

    # Add file to session as secondary
    try:
        file_manager.add_file(
            session_id=session_id,
            filename=file.filename,
            file_path=file_path,
            file_type=file_type,
            role=FileRole.SECONDARY,
            gpx_fit_metadata=gpx_fit_metadata,
            gps_quality=gps_quality,
        )
    except ValueError as e:
        # Remove the file
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Return all files
    files = file_manager.get_files(session_id)

    return UploadResponse(
        session_id=session_id,
        files=files,
    )


@router.delete("/session/{session_id}/secondary", response_model=UploadResponse)
async def remove_secondary_file(session_id: str) -> UploadResponse:
    """Remove secondary file from session."""
    if not file_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    removed = file_manager.remove_file_by_role(session_id, FileRole.SECONDARY)
    if not removed:
        raise HTTPException(status_code=404, detail="No secondary file in session")

    files = file_manager.get_files(session_id)

    return UploadResponse(
        session_id=session_id,
        files=files,
    )


@router.get("/session/{session_id}", response_model=UploadResponse)
async def get_session(session_id: str) -> UploadResponse:
    """Get session info if it still exists."""
    if not file_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found or expired")

    files = file_manager.get_files(session_id)
    if not files:
        raise HTTPException(status_code=404, detail="No files in session")

    return UploadResponse(
        session_id=session_id,
        files=files,
    )
