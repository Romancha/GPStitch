"""Templates API endpoints."""

import re

from fastapi import APIRouter, HTTPException

from gpstitch.models.editor import EditorLayout
from gpstitch.models.schemas import (
    RenameTemplateRequest,
    SaveTemplateRequest,
    SaveTemplateResponse,
    TemplateInfo,
    TemplateListResponse,
)
from gpstitch.services.template_service import template_service

router = APIRouter(prefix="/api/templates", tags=["templates"])

# Pattern for valid template names (alphanumeric, spaces, hyphens, underscores)
VALID_NAME_PATTERN = re.compile(r"^[\w\s\-]+$")
MAX_NAME_LENGTH = 200


def _validate_template_name(name: str) -> None:
    """Validate template name to prevent path traversal and invalid characters."""
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Template name cannot be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"Template name too long (max {MAX_NAME_LENGTH} characters)")
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Template name contains invalid characters")
    if not VALID_NAME_PATTERN.match(name):
        raise HTTPException(status_code=400, detail="Template name contains invalid characters")


@router.post("/save", response_model=SaveTemplateResponse)
async def save_template(request: SaveTemplateRequest) -> SaveTemplateResponse:
    """Save a custom template to filesystem."""
    _validate_template_name(request.name)

    try:
        # Convert dict to EditorLayout
        layout = EditorLayout(**request.layout)

        xml_path = template_service.save_template(
            name=request.name,
            layout=layout,
            description=request.description,
        )

        return SaveTemplateResponse(
            name=request.name,
            file_path=str(xml_path),
            success=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save template: {str(e)}") from e


@router.get("/list", response_model=TemplateListResponse)
async def list_templates() -> TemplateListResponse:
    """Get list of all saved templates."""
    try:
        templates = template_service.list_templates()
        return TemplateListResponse(templates=[TemplateInfo(**t.to_dict()) for t in templates])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}") from e


@router.get("/{name}")
async def get_template(name: str) -> dict:
    """Load a specific template."""
    _validate_template_name(name)

    try:
        layout = template_service.load_template(name)
        return {
            "layout": layout.model_dump(),
            "success": True,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load template: {str(e)}") from e


@router.get("/{name}/path")
async def get_template_path(name: str) -> dict:
    """Get the filesystem path to a template."""
    _validate_template_name(name)

    try:
        path = template_service.get_template_path(name)
        return {
            "name": name,
            "file_path": str(path),
            "success": True,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get template path: {str(e)}") from e


@router.delete("/{name}")
async def delete_template(name: str) -> dict:
    """Delete a template."""
    _validate_template_name(name)

    try:
        deleted = template_service.delete_template(name)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
        return {"success": True}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}") from e


@router.put("/{name}/rename")
async def rename_template(name: str, request: RenameTemplateRequest) -> dict:
    """Rename a template."""
    _validate_template_name(name)
    _validate_template_name(request.new_name)

    try:
        template_service.rename_template(name, request.new_name)
        return {"success": True, "new_name": request.new_name}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename template: {str(e)}") from e
