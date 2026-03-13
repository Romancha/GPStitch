"""Layouts API endpoint."""

from fastapi import APIRouter

from gpstitch.constants import is_pycairo_available
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
                requires_cairo=layout.requires_cairo,
            )
            for layout in layouts
        ],
        cairo_available=is_pycairo_available(),
    )
