"""Editor API endpoints for layout management."""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from gpstitch.models.editor import (
    EditorLayout,
    EditorPreviewRequest,
    ExportXMLRequest,
    ExportXMLResponse,
    LoadLayoutRequest,
    LoadLayoutResponse,
    SaveLayoutRequest,
    SaveLayoutResponse,
    WidgetMetadataResponse,
)
from gpstitch.services.file_manager import file_manager
from gpstitch.services.widget_registry import widget_registry
from gpstitch.services.xml_converter import xml_converter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/editor", tags=["editor"])


@router.get("/widgets", response_model=WidgetMetadataResponse)
async def get_widget_metadata() -> WidgetMetadataResponse:
    """Get metadata for all available widget types."""
    try:
        from gpstitch.constants import is_pycairo_available

        widgets = widget_registry.get_all_metadata()
        categories = widget_registry.get_categories()

        return WidgetMetadataResponse(widgets=widgets, categories=categories, cairo_available=is_pycairo_available())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/layout/save", response_model=SaveLayoutResponse)
async def save_layout(request: SaveLayoutRequest) -> SaveLayoutResponse:
    """
    Save a layout and generate XML.

    Args:
        request: Layout to save with session info

    Returns:
        Generated XML and layout ID
    """
    try:
        # Generate XML from layout
        xml = xml_converter.layout_to_xml(request.layout)

        return SaveLayoutResponse(layout_id=request.layout.id, xml=xml, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/layout/load", response_model=LoadLayoutResponse)
async def load_layout(request: LoadLayoutRequest) -> LoadLayoutResponse:
    """
    Load a layout from XML or predefined layout name.

    Args:
        request: XML string or layout name to load

    Returns:
        Parsed layout structure
    """
    try:
        if request.xml:
            # Parse provided XML
            layout = xml_converter.xml_to_layout(request.xml, "Imported Layout")
        elif request.layout_name:
            # Load predefined layout
            layout = _load_predefined_layout(request.layout_name)
        else:
            raise HTTPException(status_code=400, detail="Either 'xml' or 'layout_name' must be provided")

        return LoadLayoutResponse(layout=layout, success=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load layout: {str(e)}") from e


@router.post("/layout/load-file", response_model=LoadLayoutResponse)
async def load_layout_file(file: Annotated[UploadFile, File(...)]) -> LoadLayoutResponse:
    """
    Load a layout from uploaded XML file.

    Args:
        file: Uploaded XML file

    Returns:
        Parsed layout structure
    """
    try:
        content = await file.read()
        xml_content = content.decode("utf-8")

        # Get filename without extension for layout name
        layout_name = Path(file.filename).stem if file.filename else "Imported Layout"

        layout = xml_converter.xml_to_layout(xml_content, layout_name)

        return LoadLayoutResponse(layout=layout, success=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse XML: {str(e)}") from e


@router.post("/layout/export", response_model=ExportXMLResponse)
async def export_xml(request: ExportXMLRequest) -> ExportXMLResponse:
    """
    Export layout to XML for download.

    Args:
        request: Layout to export

    Returns:
        Formatted XML string and suggested filename
    """
    try:
        xml = xml_converter.layout_to_xml(request.layout, pretty_print=True)

        # Generate filename from layout name
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in request.layout.metadata.name)
        filename = f"{safe_name}.xml"

        return ExportXMLResponse(xml=xml, filename=filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/layout/export-download")
async def export_xml_download(request: ExportXMLRequest):
    """
    Export layout to XML file download.

    Args:
        request: Layout to export

    Returns:
        XML file as download
    """
    try:
        xml = xml_converter.layout_to_xml(request.layout, pretty_print=True)

        # Generate filename from layout name
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in request.layout.metadata.name)
        filename = f"{safe_name}.xml"

        return Response(
            content=xml,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/preview")
async def generate_preview(request: EditorPreviewRequest):
    """
    Generate a preview image for the editor layout.

    Args:
        request: Layout and session info

    Returns:
        Preview image as base64
    """
    try:
        from gpstitch.services.renderer import render_preview_from_layout

        # Get file path if session has uploaded file
        file_path = None
        gpx_path = None
        if request.session_id:
            file_path = file_manager.get_file_path(request.session_id)
            logger.debug("Editor preview: session_id=%s, file_path=%s", request.session_id, file_path)

            # If session_id was provided but file not found, return error
            # This means the session expired or file was deleted
            if not file_path or not file_path.exists():
                logger.warning("Editor preview: file not found for session %s", request.session_id)
                raise HTTPException(status_code=404, detail="Session file not found. Please re-upload your file.")

            # Get secondary GPX/FIT file if present (for videos without embedded GPS)
            secondary = file_manager.get_secondary_file(request.session_id)
            if secondary:
                gpx_path = Path(secondary.file_path)
        else:
            logger.debug("Editor preview: no session_id provided")

        preview_data = await render_preview_from_layout(
            layout=request.layout,
            file_path=file_path,
            frame_time_ms=request.frame_time_ms,
            units_speed=request.units_speed,
            units_altitude=request.units_altitude,
            units_distance=request.units_distance,
            units_temperature=request.units_temperature,
            map_style=request.map_style,
            gps_dop_max=request.gps_dop_max,
            gps_speed_max=request.gps_speed_max,
            gpx_path=gpx_path,
            video_time_alignment=request.video_time_alignment,
            time_offset_seconds=request.time_offset_seconds,
        )

        logger.debug(
            "Editor preview: generated %sx%s, base64 length=%d",
            preview_data.get("width"),
            preview_data.get("height"),
            len(preview_data.get("image_base64", "")),
        )

        return preview_data

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Preview generation failed")
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {str(e)}") from e


@router.get("/layouts")
async def get_predefined_layouts():
    """Get list of predefined layouts available for loading."""
    try:
        from gpstitch.services.renderer import get_available_layouts

        layouts = get_available_layouts()

        from gpstitch.constants import is_pycairo_available

        return {
            "layouts": [
                {
                    "name": layout.name,
                    "display_name": layout.display_name,
                    "width": layout.width,
                    "height": layout.height,
                    "requires_cairo": layout.requires_cairo,
                }
                for layout in layouts
            ],
            "cairo_available": is_pycairo_available(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _load_predefined_layout(layout_name: str) -> EditorLayout:
    """Load a predefined layout by name."""
    from importlib.resources import as_file, files

    from gopro_overlay import layouts

    from gpstitch.services.renderer import _resolve_layout_path

    # Check gpstitch custom layouts first (e.g. dji_drone_*)
    local_path = _resolve_layout_path(layout_name)
    if local_path.exists():
        xml_content = local_path.read_text(encoding="utf-8")
        return xml_converter.xml_to_layout(xml_content, layout_name)

    # Fall back to gopro-overlay package resources
    try:
        with as_file(files(layouts) / f"{layout_name}.xml") as fn, open(fn) as f:
            xml_content = f.read()

        return xml_converter.xml_to_layout(xml_content, layout_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Layout '{layout_name}' not found") from e
