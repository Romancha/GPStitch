"""Command generation API endpoint."""

import re

from fastapi import APIRouter, HTTPException

from gpstitch.models.schemas import CommandRequest, CommandResponse
from gpstitch.scripts.gopro_dashboard_wrapper import TS_SRT_SOURCE_ARG, TS_SRT_VIDEO_ARG
from gpstitch.services.file_manager import file_manager
from gpstitch.services.renderer import generate_cli_command

# Pattern to strip wrapper-internal args from user-facing commands.
# Handles both plain paths (\S+) and shell-quoted paths ('...').
_wrapper_arg_names = re.escape(TS_SRT_SOURCE_ARG) + "|" + re.escape(TS_SRT_VIDEO_ARG)
_RE_WRAPPER_ARGS = re.compile(rf"\s+(?:{_wrapper_arg_names})\s+(?:'[^']*'|\S+)")

router = APIRouter()


@router.post("/command", response_model=CommandResponse)
async def generate_command(request: CommandRequest) -> CommandResponse:
    """Generate the CLI command for full video processing."""
    # Validate session exists
    if not file_manager.session_exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    # Get the primary file path for response
    primary_file = file_manager.get_primary_file(request.session_id)
    if primary_file is None:
        raise HTTPException(status_code=404, detail="No primary file in session")

    # Extract GPX/FIT options
    gpx_merge_mode = "OVERWRITE"
    video_time_alignment = None
    if request.gpx_fit_options:
        gpx_merge_mode = request.gpx_fit_options.merge_mode
        video_time_alignment = request.gpx_fit_options.video_time_alignment

    # Generate the command (temp_files are not needed for display-only use)
    command, _temp_files = generate_cli_command(
        session_id=request.session_id,
        output_file=request.output_filename,
        layout=request.layout,
        layout_xml_path=request.layout_xml_path,
        units_speed=request.units_speed,
        units_altitude=request.units_altitude,
        units_distance=request.units_distance,
        units_temperature=request.units_temperature,
        map_style=request.map_style,
        gpx_merge_mode=gpx_merge_mode,
        video_time_alignment=video_time_alignment,
        ffmpeg_profile=request.ffmpeg_profile,
    )

    # Strip wrapper-internal args (--ts-srt-source/--ts-srt-video) from
    # user-facing command — these are only understood by the wrapper subprocess.
    user_command = _RE_WRAPPER_ARGS.sub("", command)

    return CommandResponse(
        command=user_command,
        input_file=primary_file.file_path,
    )
