"""XML conversion service - converts between editor layouts and XML."""

import xml.etree.ElementTree as ET
from typing import Any
from uuid import uuid4

from gpstitch.models.editor import (
    CanvasSettings,
    EditorLayout,
    LayoutMetadata,
    WidgetInstance,
)


class XMLConverter:
    """Bidirectional conversion between editor layouts and XML."""

    # Widget types that are containers
    CONTAINER_TYPES = {"composite", "translate", "frame"}

    # Widget types that support width/height properties
    WIDGETS_WITH_WIDTH_HEIGHT = {"bar", "zone_bar", "frame"}
    WIDGETS_WITH_HEIGHT_ONLY = {"chart"}
    WIDGETS_WITH_SIZE = {
        "moving_map",
        "journey_map",
        "moving_journey_map",
        "circuit_map",
        "compass",
        "compass_arrow",
        "asi",
        "msi",
        "gps_lock_icon",
        "icon",
        "cairo_circuit_map",
        "cairo_gauge_marker",
        "cairo_gauge_round_annotated",
        "cairo_gauge_arc_annotated",
        "cairo_gauge_donut",
    }

    # Widget types that do NOT support x,y attributes directly
    # These need to be wrapped in a translate element for positioning
    WIDGETS_WITHOUT_XY = {
        "moving_journey_map",
        "circuit_map",
        "compass",
        "compass_arrow",
        "asi",
        "msi",
        "msi2",
        "gps_lock_icon",
        # Cairo widgets also don't support x,y
        "cairo_circuit_map",
        "cairo_gauge_marker",
        "cairo_gauge_round_annotated",
        "cairo_gauge_arc_annotated",
        "cairo_gauge_donut",
    }

    def layout_to_xml(self, layout: EditorLayout, pretty_print: bool = True) -> str:
        """
        Convert an editor layout to XML string.

        Args:
            layout: The editor layout to convert
            pretty_print: Whether to format the XML with indentation

        Returns:
            XML string representation of the layout
        """
        root = ET.Element("layout")

        # Add widgets to root
        for widget in layout.widgets:
            self._widget_to_element(root, widget)

        if pretty_print:
            self._indent_xml(root)

        return ET.tostring(root, encoding="unicode")

    def xml_to_layout(self, xml_content: str, layout_name: str = "Imported Layout") -> EditorLayout:
        """
        Parse XML layout into editor format.

        Args:
            xml_content: XML string to parse
            layout_name: Name for the imported layout

        Returns:
            EditorLayout object
        """
        root = ET.fromstring(xml_content)

        widgets = []
        for elem in root:
            widget = self._element_to_widget(elem)
            if widget:
                widgets.append(widget)

        # Try to detect canvas size from layout
        width, height = self._detect_canvas_size(widgets)

        return EditorLayout(
            id=str(uuid4()),
            metadata=LayoutMetadata(name=layout_name),
            canvas=CanvasSettings(width=width, height=height),
            widgets=widgets,
        )

    def _widget_to_element(self, parent: ET.Element, widget: WidgetInstance) -> None:
        """Convert a widget instance to XML element."""
        widget_type = widget.type

        # Check if this widget type doesn't support x,y and needs a translate wrapper
        needs_translate_wrapper = (
            widget_type in self.WIDGETS_WITHOUT_XY
            and widget_type not in self.CONTAINER_TYPES
            and (widget.x != 0 or widget.y != 0)
        )

        # If widget doesn't support x,y positioning, wrap in translate element
        if needs_translate_wrapper:
            translate_elem = ET.SubElement(parent, "translate")
            if widget.x != 0:
                translate_elem.set("x", str(widget.x))
            if widget.y != 0:
                translate_elem.set("y", str(widget.y))
            parent = translate_elem

        # Determine element tag
        tag = widget_type if widget_type in self.CONTAINER_TYPES else "component"

        elem = ET.SubElement(parent, tag)

        # Add type attribute for components
        if tag == "component":
            elem.set("type", widget_type)

        # Add name if set
        if widget.name:
            elem.set("name", widget.name)

        # Add position only for widgets that support x,y attributes
        if widget_type not in self.WIDGETS_WITHOUT_XY:
            if widget.x != 0:
                elem.set("x", str(widget.x))
            if widget.y != 0:
                elem.set("y", str(widget.y))

        # Add properties
        for key, value in widget.properties.items():
            if value is not None:
                # Skip x and y as they're already added
                if key in ("x", "y"):
                    continue

                # Handle special cases
                if key == "value" and widget_type == "text":
                    # Text content goes inside the element
                    elem.text = str(value)
                elif key == "_text_content":
                    # Write as element text (for metric_unit format string, etc.)
                    elem.text = str(value)
                elif key.startswith("_"):
                    # Skip internal properties
                    continue
                elif key == "width":
                    # Only include width for widgets that support it
                    if widget_type in self.WIDGETS_WITH_WIDTH_HEIGHT:
                        elem.set(key, self._format_value(value))
                    # Skip for all other widgets
                elif key == "height":
                    # Only include height for widgets that support it
                    if widget_type in self.WIDGETS_WITH_WIDTH_HEIGHT or widget_type in self.WIDGETS_WITH_HEIGHT_ONLY:
                        elem.set(key, self._format_value(value))
                    # Skip for all other widgets
                else:
                    elem.set(key, self._format_value(value))

        # Add children for containers
        if widget.children:
            for child in widget.children:
                self._widget_to_element(elem, child)

    def _element_to_widget(self, elem: ET.Element, parent_x: int = 0, parent_y: int = 0) -> WidgetInstance | None:
        """Convert XML element to widget instance."""
        tag = elem.tag

        # Determine widget type
        if tag == "component":
            widget_type = elem.get("type", "").replace("-", "_")
        elif tag in self.CONTAINER_TYPES:
            widget_type = tag
        else:
            # Unknown tag
            return None

        # Extract position
        x = int(elem.get("x", 0))
        y = int(elem.get("y", 0))

        # Extract properties
        properties: dict[str, Any] = {}
        for key, value in elem.attrib.items():
            if key in ("type", "name", "x", "y"):
                continue
            properties[key] = self._parse_value(value)

        # Handle text content
        if elem.text and elem.text.strip():
            if widget_type == "text":
                properties["value"] = elem.text.strip()
            elif widget_type == "metric_unit":
                # Store as _text_content to be written back as element text, not attribute
                properties["_text_content"] = elem.text.strip()

        # Parse children
        children = []
        for child_elem in elem:
            child_widget = self._element_to_widget(child_elem, x, y)
            if child_widget:
                children.append(child_widget)

        return WidgetInstance(
            id=str(uuid4()),
            type=widget_type,
            name=elem.get("name"),
            x=x,
            y=y,
            properties=properties,
            children=children,
        )

    def _format_value(self, value: Any) -> str:
        """Format a Python value for XML attribute."""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (list, tuple)):
            # Color values like [255, 255, 255]
            return ",".join(str(v) for v in value)
        return str(value)

    def _parse_value(self, value: str) -> Any:
        """Parse an XML attribute value to Python type."""
        # Try to parse as number
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # Check for boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # Check for color (comma-separated numbers)
        if "," in value:
            parts = value.split(",")
            try:
                return [int(p.strip()) for p in parts]
            except ValueError:
                pass

        # Return as string
        return value

    def _detect_canvas_size(self, widgets: list[WidgetInstance]) -> tuple:
        """Detect canvas size from widget positions."""
        max_x = 1920
        max_y = 1080

        def check_widget(widget: WidgetInstance):
            nonlocal max_x, max_y
            # Estimate widget bounds
            w = widget.properties.get("width", widget.properties.get("size", 100))
            h = widget.properties.get("height", widget.properties.get("size", 50))

            if isinstance(w, (int, float)):
                max_x = max(max_x, widget.x + int(w) + 50)
            if isinstance(h, (int, float)):
                max_y = max(max_y, widget.y + int(h) + 50)

            for child in widget.children:
                check_widget(child)

        for widget in widgets:
            check_widget(widget)

        return max_x, max_y

    def _indent_xml(self, elem: ET.Element, level: int = 0) -> None:
        """Add indentation to XML element for pretty printing."""
        indent = "\n" + "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            for child in elem:
                self._indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent


# Singleton instance
xml_converter = XMLConverter()
