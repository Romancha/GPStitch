"""Layouts API endpoint."""

from fastapi import APIRouter

from gpstitch.models.schemas import LayoutInfo, LayoutsResponse
from gpstitch.services.renderer import get_available_layouts

router = APIRouter()


@router.get("/layouts", response_model=LayoutsResponse)
async def get_layouts() -> LayoutsResponse:
    """Get list of available dashboard layouts."""
    layouts = get_available_layouts()
    return LayoutsResponse(
        layouts=[
            LayoutInfo(
                name=layout.name,
                display_name=layout.display_name,
                width=layout.width,
                height=layout.height,
            )
            for layout in layouts
        ]
    )
