"""Template management service - filesystem-based template storage."""

import json
import re
from datetime import datetime
from pathlib import Path

from gpstitch.config import settings
from gpstitch.models.editor import EditorLayout
from gpstitch.services.xml_converter import xml_converter


class TemplateInfo:
    """Information about a saved template."""

    def __init__(
        self,
        name: str,
        file_path: str,
        created_at: str | None = None,
        modified_at: str | None = None,
        canvas_width: int = 1920,
        canvas_height: int = 1080,
        description: str | None = None,
    ):
        self.name = name
        self.file_path = file_path
        self.created_at = created_at or datetime.now().isoformat()
        self.modified_at = modified_at or datetime.now().isoformat()
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.description = description

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "description": self.description,
        }


class TemplateService:
    """Manages custom template storage in filesystem."""

    def __init__(self, templates_dir: Path | None = None):
        self.templates_dir = templates_dir or settings.templates_dir
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_name(self, name: str) -> str:
        """Sanitize template name for filesystem."""
        if not name or not name.strip():
            raise ValueError("Template name cannot be empty")
        # Replace invalid characters with underscores
        safe_name = re.sub(r"[^\w\s\-]", "_", name)
        # Replace multiple spaces/underscores with single underscore
        safe_name = re.sub(r"[\s_]+", "_", safe_name)
        safe_name = safe_name.strip("_")
        if not safe_name:
            raise ValueError("Template name results in empty filename after sanitization")
        # Limit length to prevent filesystem issues
        if len(safe_name) > 200:
            safe_name = safe_name[:200]
        return safe_name

    def _validate_path_within_templates_dir(self, path: Path) -> Path:
        """Ensure the path is within the templates directory (prevents path traversal)."""
        resolved = path.resolve()
        templates_dir_resolved = self.templates_dir.resolve()
        # Check that the resolved path starts with templates directory
        try:
            resolved.relative_to(templates_dir_resolved)
        except ValueError as e:
            raise ValueError("Invalid template path: path escapes templates directory") from e
        return resolved

    def _get_xml_path(self, name: str) -> Path:
        """Get path to template XML file."""
        safe_name = self._sanitize_name(name)
        xml_path = self.templates_dir / f"{safe_name}.xml"
        # Validate path is within templates_dir
        self._validate_path_within_templates_dir(xml_path)
        return xml_path

    def _get_metadata_path(self, name: str) -> Path:
        """Get path to template metadata file."""
        safe_name = self._sanitize_name(name)
        meta_path = self.templates_dir / f"{safe_name}.json"
        # Validate path is within templates_dir
        self._validate_path_within_templates_dir(meta_path)
        return meta_path

    def save_template(
        self,
        name: str,
        layout: EditorLayout,
        description: str | None = None,
    ) -> Path:
        """
        Save a template to filesystem.

        Args:
            name: Template name
            layout: EditorLayout object
            description: Optional description

        Returns:
            Path to saved XML file
        """
        # Convert layout to XML
        xml_content = xml_converter.layout_to_xml(layout, pretty_print=True)

        # Save XML file
        xml_path = self._get_xml_path(name)
        xml_path.write_text(xml_content, encoding="utf-8")

        # Create metadata
        now = datetime.now().isoformat()
        metadata = {
            "name": name,
            "created_at": now,
            "modified_at": now,
            "canvas_width": layout.canvas.width,
            "canvas_height": layout.canvas.height,
            "description": description or (layout.metadata.description if layout.metadata else None),
        }

        # If updating existing template, preserve created_at
        metadata_path = self._get_metadata_path(name)
        if metadata_path.exists():
            try:
                existing = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata["created_at"] = existing.get("created_at", now)
            except (json.JSONDecodeError, ValueError, KeyError):
                pass  # Use new timestamp on JSON parsing errors only

        # Save metadata
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return xml_path

    def load_template(self, name: str) -> EditorLayout:
        """
        Load a template from filesystem.

        Args:
            name: Template name

        Returns:
            EditorLayout object

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        xml_path = self._get_xml_path(name)

        if not xml_path.exists():
            raise FileNotFoundError(f"Template '{name}' not found")

        xml_content = xml_path.read_text(encoding="utf-8")
        layout = xml_converter.xml_to_layout(xml_content, name)

        # Override canvas size from metadata if available
        metadata_path = self._get_metadata_path(name)
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if "canvas_width" in metadata and "canvas_height" in metadata:
                    layout.canvas.width = metadata["canvas_width"]
                    layout.canvas.height = metadata["canvas_height"]
            except (json.JSONDecodeError, ValueError):
                pass  # Use auto-detected size on error

        return layout

    def get_template_path(self, name: str) -> Path:
        """
        Get absolute path to template XML file.

        Args:
            name: Template name

        Returns:
            Absolute path to XML file

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        xml_path = self._get_xml_path(name)
        if not xml_path.exists():
            raise FileNotFoundError(f"Template '{name}' not found")
        return xml_path.resolve()

    def list_templates(self) -> list[TemplateInfo]:
        """
        List all available templates.

        Returns:
            List of TemplateInfo objects
        """
        templates = []

        for xml_file in self.templates_dir.glob("*.xml"):
            metadata_file = xml_file.with_suffix(".json")

            # Load metadata if exists
            if metadata_file.exists():
                try:
                    metadata_dict = json.loads(metadata_file.read_text(encoding="utf-8"))
                    info = TemplateInfo(
                        name=metadata_dict.get("name", xml_file.stem),
                        file_path=str(xml_file.resolve()),
                        created_at=metadata_dict.get("created_at"),
                        modified_at=metadata_dict.get("modified_at"),
                        canvas_width=metadata_dict.get("canvas_width", 1920),
                        canvas_height=metadata_dict.get("canvas_height", 1080),
                        description=metadata_dict.get("description"),
                    )
                except (json.JSONDecodeError, ValueError, KeyError):
                    # Fallback to basic info on JSON parsing errors
                    info = TemplateInfo(
                        name=xml_file.stem,
                        file_path=str(xml_file.resolve()),
                    )
            else:
                info = TemplateInfo(
                    name=xml_file.stem,
                    file_path=str(xml_file.resolve()),
                )

            templates.append(info)

        # Sort by modified time, most recent first
        templates.sort(key=lambda t: t.modified_at or "", reverse=True)
        return templates

    def delete_template(self, name: str) -> bool:
        """
        Delete a template.

        Args:
            name: Template name

        Returns:
            True if deleted, False if not found
        """
        xml_path = self._get_xml_path(name)
        metadata_path = self._get_metadata_path(name)

        deleted = False
        if xml_path.exists():
            xml_path.unlink()
            deleted = True
        if metadata_path.exists():
            metadata_path.unlink()

        return deleted

    def rename_template(self, old_name: str, new_name: str) -> bool:
        """
        Rename a template.

        Args:
            old_name: Current template name
            new_name: New template name

        Returns:
            True if renamed successfully

        Raises:
            FileNotFoundError: If old template doesn't exist
            FileExistsError: If new name already exists
        """
        old_xml = self._get_xml_path(old_name)
        old_meta = self._get_metadata_path(old_name)
        new_xml = self._get_xml_path(new_name)
        new_meta = self._get_metadata_path(new_name)

        if not old_xml.exists():
            raise FileNotFoundError(f"Template '{old_name}' not found")

        # Use atomic rename with exception handling instead of exists() check
        # This prevents TOCTOU race condition
        try:
            # Attempt to rename - will fail if target exists
            old_xml.rename(new_xml)
        except FileExistsError as e:
            raise FileExistsError(f"Template '{new_name}' already exists") from e

        # Update metadata
        if old_meta.exists():
            try:
                metadata_dict = json.loads(old_meta.read_text(encoding="utf-8"))
                metadata_dict["name"] = new_name
                metadata_dict["modified_at"] = datetime.now().isoformat()
                new_meta.write_text(json.dumps(metadata_dict, indent=2), encoding="utf-8")
                old_meta.unlink()
            except (json.JSONDecodeError, ValueError, KeyError):
                # If metadata parsing fails, just rename the file
                old_meta.rename(new_meta)

        return True

    def template_exists(self, name: str) -> bool:
        """Check if a template exists."""
        return self._get_xml_path(name).exists()


# Global instance
template_service = TemplateService()
