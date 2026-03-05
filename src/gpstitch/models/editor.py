"""Editor-specific data models."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from gpstitch.constants import (
    DEFAULT_GPS_DOP_MAX,
    DEFAULT_GPS_SPEED_MAX,
    DEFAULT_UNITS_ALTITUDE,
    DEFAULT_UNITS_DISTANCE,
    DEFAULT_UNITS_SPEED,
    DEFAULT_UNITS_TEMPERATURE,
)


class PropertyType(str, Enum):
    """Supported property types."""

    NUMBER = "number"
    STRING = "string"
    BOOLEAN = "boolean"
    COLOR = "color"
    SELECT = "select"
    METRIC = "metric"
    UNITS = "units"


class WidgetCategory(str, Enum):
    """Widget categories for organization."""

    TEXT = "text"
    METRICS = "metrics"
    MAPS = "maps"
    GAUGES = "gauges"
    CHARTS = "charts"
    INDICATORS = "indicators"
    CONTAINERS = "containers"
    CAIRO = "cairo"


class PropertyConstraints(BaseModel):
    """Validation constraints for a property."""

    min: float | None = None
    max: float | None = None
    step: float | None = None
    required: bool = False
    default: Any | None = None


class SelectOption(BaseModel):
    """Option for select-type properties."""

    value: str
    label: str


class PropertyDefinition(BaseModel):
    """Definition of a single widget property."""

    name: str
    label: str
    type: PropertyType
    description: str | None = None
    constraints: PropertyConstraints | None = None
    options: list[SelectOption] | None = None
    category: str = "General"


class WidgetMetadata(BaseModel):
    """Complete metadata for a widget type."""

    type: str
    name: str
    description: str
    category: WidgetCategory
    icon: str | None = None
    properties: list[PropertyDefinition]
    default_width: int = 100
    default_height: int = 50
    is_container: bool = False
    requires_cairo: bool = False


class WidgetMetadataResponse(BaseModel):
    """Response containing all widget metadata."""

    widgets: list[WidgetMetadata]
    categories: list[str]


class WidgetInstance(BaseModel):
    """A widget instance in the layout."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    name: str | None = None
    x: int = 0
    y: int = 0
    properties: dict[str, Any] = Field(default_factory=dict)
    children: list[WidgetInstance] = Field(default_factory=list)
    locked: bool = False
    visible: bool = True


WidgetInstance.model_rebuild()


class CanvasSettings(BaseModel):
    """Canvas/layout settings."""

    width: int = 1920
    height: int = 1080
    grid_enabled: bool = True
    grid_size: int = 10
    snap_to_grid: bool = False


class LayoutMetadata(BaseModel):
    """Layout metadata."""

    name: str = "Untitled Layout"
    description: str | None = None
    version: str = "1.0"


class EditorLayout(BaseModel):
    """Complete layout definition for editor."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    metadata: LayoutMetadata = Field(default_factory=LayoutMetadata)
    canvas: CanvasSettings = Field(default_factory=CanvasSettings)
    widgets: list[WidgetInstance] = Field(default_factory=list)


class SaveLayoutRequest(BaseModel):
    """Request to save a layout."""

    session_id: str
    layout: EditorLayout


class SaveLayoutResponse(BaseModel):
    """Response from save layout."""

    layout_id: str
    xml: str
    success: bool = True


class LoadLayoutRequest(BaseModel):
    """Request to load a layout from XML."""

    session_id: str
    xml: str | None = None
    layout_name: str | None = None


class LoadLayoutResponse(BaseModel):
    """Response from load layout."""

    layout: EditorLayout
    success: bool = True


class ExportXMLRequest(BaseModel):
    """Request to export layout to XML."""

    layout: EditorLayout


class ExportXMLResponse(BaseModel):
    """Response from XML export."""

    xml: str
    filename: str


class EditorPreviewRequest(BaseModel):
    """Request for generating preview from editor layout."""

    session_id: str
    layout: EditorLayout
    frame_time_ms: int = 0
    units_speed: str = DEFAULT_UNITS_SPEED
    units_altitude: str = DEFAULT_UNITS_ALTITUDE
    units_distance: str = DEFAULT_UNITS_DISTANCE
    units_temperature: str = DEFAULT_UNITS_TEMPERATURE
    map_style: str | None = None
    gps_dop_max: float = DEFAULT_GPS_DOP_MAX
    gps_speed_max: float = DEFAULT_GPS_SPEED_MAX
