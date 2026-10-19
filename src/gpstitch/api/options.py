"""Options API endpoints for units, map styles, fonts, and FFmpeg profiles."""

from fastapi import APIRouter, HTTPException, Response
from fastapi.concurrency import run_in_threadpool

from gpstitch.models.schemas import (
    FFmpegProfileOption,
    FFmpegProfilesResponse,
    FontsResponse,
    MapStyleOption,
    MapStylesResponse,
    UnitCategory,
    UnitOption,
    UnitOptionsResponse,
)
from gpstitch.services.font_service import font_service
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


@router.get("/options/fonts", response_model=FontsResponse)
async def get_fonts() -> FontsResponse:
    """Get fonts installed on the system."""
    fonts = await run_in_threadpool(font_service.list_fonts)
    return FontsResponse(fonts=fonts)


@router.get("/options/fonts/{font_id}/preview.png")
async def get_font_preview(font_id: str) -> Response:
    """Render the font's family name in its own face for the font picker.

    Rendered with PIL like the overlay itself, so every face of a .ttc collection
    shows correctly (browsers can't pick a face out of a collection).
    """
    font = await run_in_threadpool(font_service.get_font, font_id)
    if font is None:
        raise HTTPException(status_code=404, detail="Font not found")
    try:
        png = await run_in_threadpool(font_service.render_preview, font)
    except OSError as e:
        raise HTTPException(status_code=404, detail="Font can't be rendered") from e
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


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
