"""Unit tests for WidgetRegistry service."""

from gpstitch.models.editor import WidgetCategory
from gpstitch.services.widget_registry import widget_registry


class TestWidgetRegistryMetadata:
    """Tests for widget metadata retrieval."""

    def test_get_metadata_text(self):
        """Get metadata for text widget."""
        metadata = widget_registry.get_metadata("text")

        assert metadata is not None
        assert metadata.type == "text"
        assert metadata.name == "Text"
        assert metadata.category == WidgetCategory.TEXT

    def test_get_metadata_metric(self):
        """Get metadata for metric widget."""
        metadata = widget_registry.get_metadata("metric")

        assert metadata is not None
        assert metadata.type == "metric"
        assert metadata.category == WidgetCategory.METRICS

    def test_get_metadata_moving_map(self):
        """Get metadata for moving_map widget."""
        metadata = widget_registry.get_metadata("moving_map")

        assert metadata is not None
        assert metadata.type == "moving_map"
        assert metadata.category == WidgetCategory.MAPS

    def test_get_metadata_nonexistent(self):
        """Getting nonexistent widget returns None."""
        metadata = widget_registry.get_metadata("nonexistent_widget")

        assert metadata is None

    def test_get_all_metadata(self):
        """Get all widget metadata."""
        all_widgets = widget_registry.get_all_metadata()

        assert len(all_widgets) > 20  # Many widgets defined
        types = [w.type for w in all_widgets]
        assert "text" in types
        assert "metric" in types
        assert "moving_map" in types
        assert "compass" in types
        assert "chart" in types


class TestWidgetRegistryCategories:
    """Tests for widget categories."""

    def test_get_categories(self):
        """Get all categories."""
        categories = widget_registry.get_categories()

        assert len(categories) == len(WidgetCategory)
        assert "text" in categories
        assert "metrics" in categories
        assert "maps" in categories
        assert "gauges" in categories
        assert "charts" in categories
        assert "containers" in categories
        assert "cairo" in categories

    def test_widgets_have_categories(self):
        """All widgets have valid categories."""
        all_widgets = widget_registry.get_all_metadata()
        valid_categories = set(WidgetCategory)

        for widget in all_widgets:
            assert widget.category in valid_categories


class TestWidgetRegistryProperties:
    """Tests for widget properties."""

    def test_text_widget_has_value_property(self):
        """Text widget has value property."""
        metadata = widget_registry.get_metadata("text")
        prop_names = [p.name for p in metadata.properties]

        assert "value" in prop_names

    def test_metric_widget_has_metric_property(self):
        """Metric widget has metric and units properties."""
        metadata = widget_registry.get_metadata("metric")
        prop_names = [p.name for p in metadata.properties]

        assert "metric" in prop_names
        assert "units" in prop_names

    def test_moving_map_has_zoom_property(self):
        """Moving map widget has zoom property."""
        metadata = widget_registry.get_metadata("moving_map")
        prop_names = [p.name for p in metadata.properties]

        assert "zoom" in prop_names
        assert "size" in prop_names

    def test_all_widgets_have_position_properties(self):
        """All widgets have x and y properties."""
        all_widgets = widget_registry.get_all_metadata()

        for widget in all_widgets:
            prop_names = [p.name for p in widget.properties]
            assert "x" in prop_names, f"{widget.type} missing x"
            assert "y" in prop_names, f"{widget.type} missing y"

    def test_properties_have_defaults(self):
        """Properties with constraints have defaults."""
        metadata = widget_registry.get_metadata("metric")

        for prop in metadata.properties:
            if prop.constraints and prop.constraints.required:
                assert prop.constraints.default is not None, f"{prop.name} missing default"


class TestWidgetRegistryContainers:
    """Tests for container widgets."""

    def test_composite_is_container(self):
        """Composite widget is marked as container."""
        metadata = widget_registry.get_metadata("composite")

        assert metadata.is_container is True

    def test_translate_is_container(self):
        """Translate widget is marked as container."""
        metadata = widget_registry.get_metadata("translate")

        assert metadata.is_container is True

    def test_frame_is_container(self):
        """Frame widget is marked as container."""
        metadata = widget_registry.get_metadata("frame")

        assert metadata.is_container is True

    def test_text_is_not_container(self):
        """Text widget is not a container."""
        metadata = widget_registry.get_metadata("text")

        assert metadata.is_container is False


class TestWidgetRegistryCairo:
    """Tests for Cairo widgets."""

    def test_cairo_widgets_require_cairo(self):
        """Cairo widgets are marked as requiring Cairo."""
        cairo_types = [
            "cairo_circuit_map",
            "cairo_gauge_marker",
            "cairo_gauge_round_annotated",
            "cairo_gauge_arc_annotated",
            "cairo_gauge_donut",
        ]

        for widget_type in cairo_types:
            metadata = widget_registry.get_metadata(widget_type)
            assert metadata is not None, f"{widget_type} not found"
            assert metadata.requires_cairo is True, f"{widget_type} should require Cairo"

    def test_regular_widgets_dont_require_cairo(self):
        """Regular widgets don't require Cairo."""
        regular_types = ["text", "metric", "moving_map", "compass", "chart"]

        for widget_type in regular_types:
            metadata = widget_registry.get_metadata(widget_type)
            assert metadata.requires_cairo is False, f"{widget_type} should not require Cairo"


class TestWidgetRegistryDefaults:
    """Tests for widget default sizes."""

    def test_widgets_have_default_dimensions(self):
        """All widgets have default width and height."""
        all_widgets = widget_registry.get_all_metadata()

        for widget in all_widgets:
            assert widget.default_width > 0, f"{widget.type} missing default_width"
            assert widget.default_height > 0, f"{widget.type} missing default_height"

    def test_map_widgets_are_square(self):
        """Map widgets have equal width and height."""
        map_types = ["moving_map", "journey_map", "moving_journey_map", "circuit_map"]

        for widget_type in map_types:
            metadata = widget_registry.get_metadata(widget_type)
            assert metadata.default_width == metadata.default_height, f"{widget_type} should be square"

    def test_text_widget_reasonable_size(self):
        """Text widget has reasonable default size."""
        metadata = widget_registry.get_metadata("text")

        assert metadata.default_width >= 50
        assert metadata.default_height >= 20
