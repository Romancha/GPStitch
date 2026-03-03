"""Unit tests for XMLConverter service."""

from gpstitch.services.xml_converter import xml_converter


class TestLayoutToXml:
    """Tests for layout to XML conversion."""

    def test_converts_basic_layout(self, sample_editor_layout):
        """Convert basic layout to XML."""
        xml = xml_converter.layout_to_xml(sample_editor_layout)

        assert "<layout>" in xml
        assert "</layout>" in xml
        assert 'type="text"' in xml
        assert 'type="metric"' in xml

    def test_includes_position(self, sample_editor_layout):
        """XML should include widget positions."""
        xml = xml_converter.layout_to_xml(sample_editor_layout)

        assert 'x="100"' in xml
        assert 'y="50"' in xml or 'y="100"' in xml

    def test_includes_properties(self, sample_editor_layout):
        """XML should include widget properties."""
        xml = xml_converter.layout_to_xml(sample_editor_layout)

        # Text widget properties
        assert 'size="32"' in xml or "size=" in xml
        # Metric widget properties
        assert 'metric="speed"' in xml
        assert 'units="kph"' in xml

    def test_text_content_in_element(self, layout_factory, widget_factory):
        """Text widget value should be element content."""
        widget = widget_factory(widget_type="text", properties={"value": "Hello World"})
        layout = layout_factory(widgets=[widget])

        xml = xml_converter.layout_to_xml(layout)

        assert ">Hello World<" in xml

    def test_omits_zero_position(self, layout_factory, widget_factory):
        """Zero position should be omitted from XML."""
        widget = widget_factory(widget_type="text", x=0, y=0)
        layout = layout_factory(widgets=[widget])

        xml = xml_converter.layout_to_xml(layout)

        # x="0" and y="0" should not appear
        lines = [line for line in xml.split("\n") if 'type="text"' in line]
        for line in lines:
            assert 'x="0"' not in line
            assert 'y="0"' not in line

    def test_container_types_use_tag_name(self, layout_factory, widget_factory):
        """Container widgets use their type as tag name."""
        widget = widget_factory(widget_type="composite", x=50, y=50)
        widget.children = [widget_factory(widget_type="text", x=0, y=0)]
        layout = layout_factory(widgets=[widget])

        xml = xml_converter.layout_to_xml(layout)

        assert "<composite" in xml
        assert "</composite>" in xml

    def test_widgets_without_xy_wrapped_in_translate(self, layout_factory, widget_factory):
        """Widgets that don't support x,y should be wrapped in translate."""
        # compass is in WIDGETS_WITHOUT_XY
        widget = widget_factory(widget_type="compass", x=200, y=200, properties={"size": 256})
        layout = layout_factory(widgets=[widget])

        xml = xml_converter.layout_to_xml(layout)

        assert "<translate" in xml
        assert 'x="200"' in xml
        assert 'y="200"' in xml
        assert 'type="compass"' in xml

    def test_pretty_print(self, sample_editor_layout):
        """Pretty print should add indentation."""
        xml = xml_converter.layout_to_xml(sample_editor_layout, pretty_print=True)

        assert "\n" in xml
        # Should have indentation
        lines = xml.split("\n")
        indented_lines = [line for line in lines if line.startswith("  ")]
        assert len(indented_lines) > 0

    def test_no_pretty_print(self, sample_editor_layout):
        """Without pretty print, no extra whitespace."""
        xml = xml_converter.layout_to_xml(sample_editor_layout, pretty_print=False)

        # Should be more compact
        assert xml.startswith("<layout>")


class TestXmlToLayout:
    """Tests for XML to layout conversion."""

    def test_parses_basic_xml(self, sample_xml_layout):
        """Parse basic XML layout."""
        layout = xml_converter.xml_to_layout(sample_xml_layout, "Test Layout")

        assert layout.metadata.name == "Test Layout"
        assert len(layout.widgets) == 2

    def test_parses_widget_types(self, sample_xml_layout):
        """Parsed widgets have correct types."""
        layout = xml_converter.xml_to_layout(sample_xml_layout, "Test")

        types = [w.type for w in layout.widgets]
        assert "text" in types
        assert "metric" in types

    def test_parses_positions(self, sample_xml_layout):
        """Parsed widgets have correct positions."""
        layout = xml_converter.xml_to_layout(sample_xml_layout, "Test")

        text_widget = next(w for w in layout.widgets if w.type == "text")
        assert text_widget.x == 100
        assert text_widget.y == 50

    def test_parses_properties(self, sample_xml_layout):
        """Parsed widgets have correct properties."""
        layout = xml_converter.xml_to_layout(sample_xml_layout, "Test")

        metric_widget = next(w for w in layout.widgets if w.type == "metric")
        assert metric_widget.properties.get("metric") == "speed"
        assert metric_widget.properties.get("units") == "kph"

    def test_parses_text_content(self):
        """Text element content should become 'value' property."""
        xml = '<layout><component type="text" x="0" y="0">Hello</component></layout>'

        layout = xml_converter.xml_to_layout(xml, "Test")

        text_widget = layout.widgets[0]
        assert text_widget.properties.get("value") == "Hello"

    def test_parses_container_children(self):
        """Container children should be parsed."""
        xml = """<layout>
            <composite x="10" y="10">
                <component type="text" x="0" y="0">Child</component>
            </composite>
        </layout>"""

        layout = xml_converter.xml_to_layout(xml, "Test")

        assert len(layout.widgets) == 1
        composite = layout.widgets[0]
        assert composite.type == "composite"
        assert len(composite.children) == 1
        assert composite.children[0].type == "text"

    def test_generates_widget_ids(self, sample_xml_layout):
        """Parsed widgets should have generated IDs."""
        layout = xml_converter.xml_to_layout(sample_xml_layout, "Test")

        for widget in layout.widgets:
            assert widget.id
            assert len(widget.id) == 36  # UUID format

    def test_detects_canvas_size(self, sample_xml_layout):
        """Canvas size should be detected from widget positions."""
        layout = xml_converter.xml_to_layout(sample_xml_layout, "Test")

        # Default minimum is 1920x1080
        assert layout.canvas.width >= 1920
        assert layout.canvas.height >= 1080


class TestRoundtrip:
    """Tests for layout -> XML -> layout roundtrip."""

    def test_basic_roundtrip(self, sample_editor_layout):
        """Layout should survive roundtrip conversion."""
        xml = xml_converter.layout_to_xml(sample_editor_layout)
        restored = xml_converter.xml_to_layout(xml, "Restored")

        assert len(restored.widgets) == len(sample_editor_layout.widgets)

    def test_widget_types_preserved(self, sample_editor_layout):
        """Widget types should be preserved in roundtrip."""
        xml = xml_converter.layout_to_xml(sample_editor_layout)
        restored = xml_converter.xml_to_layout(xml, "Restored")

        original_types = sorted([w.type for w in sample_editor_layout.widgets])
        restored_types = sorted([w.type for w in restored.widgets])
        assert original_types == restored_types

    def test_positions_preserved(self, sample_editor_layout):
        """Widget positions should be preserved in roundtrip."""
        xml = xml_converter.layout_to_xml(sample_editor_layout)
        restored = xml_converter.xml_to_layout(xml, "Restored")

        for original, restored_w in zip(
            sorted(sample_editor_layout.widgets, key=lambda w: w.type),
            sorted(restored.widgets, key=lambda w: w.type),
            strict=True,
        ):
            assert original.x == restored_w.x
            assert original.y == restored_w.y

    def test_container_children_preserved(self, layout_factory, widget_factory):
        """Container children should be preserved."""
        child = widget_factory(widget_type="text", x=10, y=10)
        container = widget_factory(widget_type="composite", x=0, y=0)
        container.children = [child]
        layout = layout_factory(widgets=[container])

        xml = xml_converter.layout_to_xml(layout)
        restored = xml_converter.xml_to_layout(xml, "Restored")

        assert len(restored.widgets) == 1
        assert len(restored.widgets[0].children) == 1
        assert restored.widgets[0].children[0].type == "text"


class TestValueFormatting:
    """Tests for value formatting and parsing."""

    def test_format_boolean_true(self):
        """Boolean True should format as 'true'."""
        result = xml_converter._format_value(True)
        assert result == "true"

    def test_format_boolean_false(self):
        """Boolean False should format as 'false'."""
        result = xml_converter._format_value(False)
        assert result == "false"

    def test_format_list_as_comma_separated(self):
        """List should format as comma-separated."""
        result = xml_converter._format_value([255, 128, 0])
        assert result == "255,128,0"

    def test_parse_integer(self):
        """Integer string should parse to int."""
        result = xml_converter._parse_value("42")
        assert result == 42
        assert isinstance(result, int)

    def test_parse_float(self):
        """Float string should parse to float."""
        result = xml_converter._parse_value("3.14")
        assert result == 3.14
        assert isinstance(result, float)

    def test_parse_boolean_true(self):
        """'true' should parse to True."""
        assert xml_converter._parse_value("true") is True
        assert xml_converter._parse_value("yes") is True
        # "1" parses as integer 1, not boolean
        assert xml_converter._parse_value("1") == 1

    def test_parse_boolean_false(self):
        """'false' should parse to False."""
        assert xml_converter._parse_value("false") is False
        assert xml_converter._parse_value("no") is False
        # "0" parses as integer 0, not boolean
        assert xml_converter._parse_value("0") == 0

    def test_parse_color_list(self):
        """Comma-separated numbers should parse to list."""
        result = xml_converter._parse_value("255,128,0")
        assert result == [255, 128, 0]

    def test_parse_string(self):
        """Regular string should remain string."""
        result = xml_converter._parse_value("hello")
        assert result == "hello"
        assert isinstance(result, str)
