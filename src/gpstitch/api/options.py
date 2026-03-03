"""Options API endpoints for units, map styles, and FFmpeg profiles."""

from fastapi import APIRouter

from gpstitch.models.schemas import (
    FFmpegProfileOption,
    FFmpegProfilesResponse,
    MapStyleOption,
    MapStylesResponse,
    UnitCategory,
    UnitOption,
    UnitOptionsResponse,
)
from gpstitch.services.renderer import (
    get_available_ffmpeg_profiles,
    get_available_map_styles,
    get_available_units,
)

router = APIRouter()


@router.get("/options/units", response_model=UnitOptionsResponse)
async def get_unit_options() -> UnitOptionsResponse:
    """Get available unit options for speed, altitude, distance, and temperature."""
    units = get_available_units()

    categories = []
    for name, category_data in units.items():
        options = [UnitOption(value=opt["value"], label=opt["label"]) for opt in category_data["options"]]
        categories.append(
            UnitCategory(
                name=name,
                label=category_data["label"],
                options=options,
                default=category_data["default"],
            )
        )

    return UnitOptionsResponse(categories=categories)


@router.get("/options/map-styles", response_model=MapStylesResponse)
async def get_map_styles() -> MapStylesResponse:
    """Get available map styles."""
    styles = get_available_map_styles()
    return MapStylesResponse(
        styles=[
            MapStyleOption(
                name=s["name"], display_name=s["display_name"], requires_api_key=s.get("requires_api_key", False)
            )
            for s in styles
        ]
    )


@router.get("/options/ffmpeg-profiles", response_model=FFmpegProfilesResponse)
async def get_ffmpeg_profiles() -> FFmpegProfilesResponse:
    """Get available FFmpeg encoding profiles."""
    profiles = get_available_ffmpeg_profiles()
    return FFmpegProfilesResponse(
        profiles=[
            FFmpegProfileOption(
                name=p["name"],
                display_name=p["display_name"],
                description=p["description"],
                is_builtin=p.get("is_builtin", True),
            )
            for p in profiles
        ]
    )
