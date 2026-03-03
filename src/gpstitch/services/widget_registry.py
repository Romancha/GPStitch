"""Widget metadata registry - defines all available widgets and their properties."""

from gpstitch.models.editor import (
    PropertyConstraints,
    PropertyDefinition,
    PropertyType,
    SelectOption,
    WidgetCategory,
    WidgetMetadata,
)

# Available metrics from layout_xml.py metric_accessor_from
AVAILABLE_METRICS = [
    SelectOption(value="speed", label="Speed"),
    SelectOption(value="cspeed", label="Calculated Speed"),
    SelectOption(value="alt", label="Altitude"),
    SelectOption(value="hr", label="Heart Rate"),
    SelectOption(value="cadence", label="Cadence"),
    SelectOption(value="power", label="Power"),
    SelectOption(value="temp", label="Temperature"),
    SelectOption(value="gradient", label="Gradient"),
    SelectOption(value="cgrad", label="Calculated Gradient"),
    SelectOption(value="azi", label="Azimuth"),
    SelectOption(value="cog", label="Course Over Ground"),
    SelectOption(value="odo", label="Odometer"),
    SelectOption(value="codo", label="Calculated Odometer"),
    SelectOption(value="dist", label="Distance"),
    SelectOption(value="accel", label="Acceleration"),
    SelectOption(value="accl.x", label="Acceleration X"),
    SelectOption(value="accl.y", label="Acceleration Y"),
    SelectOption(value="accl.z", label="Acceleration Z"),
    SelectOption(value="grav.x", label="Gravity X"),
    SelectOption(value="grav.y", label="Gravity Y"),
    SelectOption(value="grav.z", label="Gravity Z"),
    SelectOption(value="ori.pitch", label="Orientation Pitch"),
    SelectOption(value="ori.roll", label="Orientation Roll"),
    SelectOption(value="ori.yaw", label="Orientation Yaw"),
    SelectOption(value="lat", label="Latitude"),
    SelectOption(value="lon", label="Longitude"),
    SelectOption(value="gps-dop", label="GPS DOP"),
    SelectOption(value="gps-lock", label="GPS Lock"),
    SelectOption(value="respiration", label="Respiration"),
    SelectOption(value="gear.front", label="Gear Front"),
    SelectOption(value="gear.rear", label="Gear Rear"),
]

# Available units from layout_xml.py Converters
AVAILABLE_UNITS = [
    SelectOption(value="none", label="None"),
    SelectOption(value="mph", label="mph"),
    SelectOption(value="kph", label="km/h"),
    SelectOption(value="knots", label="Knots"),
    SelectOption(value="speed", label="Speed (user setting)"),
    SelectOption(value="pace", label="Pace"),
    SelectOption(value="pace_mile", label="Pace (mile)"),
    SelectOption(value="pace_km", label="Pace (km)"),
    SelectOption(value="metres", label="Metres"),
    SelectOption(value="feet", label="Feet"),
    SelectOption(value="miles", label="Miles"),
    SelectOption(value="altitude", label="Altitude (user setting)"),
    SelectOption(value="distance", label="Distance (user setting)"),
    SelectOption(value="G", label="G-force"),
    SelectOption(value="temp", label="Temperature (user setting)"),
]


def _common_position_props() -> list[PropertyDefinition]:
    """Common position properties for all widgets."""
    return [
        PropertyDefinition(
            name="x",
            label="X Position",
            type=PropertyType.NUMBER,
            constraints=PropertyConstraints(default=0),
            category="Position",
        ),
        PropertyDefinition(
            name="y",
            label="Y Position",
            type=PropertyType.NUMBER,
            constraints=PropertyConstraints(default=0),
            category="Position",
        ),
    ]


def _common_text_props() -> list[PropertyDefinition]:
    """Common text styling properties."""
    return [
        PropertyDefinition(
            name="size",
            label="Font Size",
            type=PropertyType.NUMBER,
            constraints=PropertyConstraints(min=8, max=500, default=16),
            category="Appearance",
        ),
        PropertyDefinition(
            name="rgb",
            label="Text Color",
            type=PropertyType.COLOR,
            constraints=PropertyConstraints(default="255,255,255"),
            category="Appearance",
        ),
        PropertyDefinition(
            name="outline",
            label="Outline Color",
            type=PropertyType.COLOR,
            constraints=PropertyConstraints(default="0,0,0"),
            category="Appearance",
        ),
        PropertyDefinition(
            name="outline_width",
            label="Outline Width",
            type=PropertyType.NUMBER,
            constraints=PropertyConstraints(min=0, max=20, default=2),
            category="Appearance",
        ),
        PropertyDefinition(
            name="align",
            label="Alignment",
            type=PropertyType.SELECT,
            options=[
                SelectOption(value="left", label="Left"),
                SelectOption(value="centre", label="Center"),
                SelectOption(value="right", label="Right"),
            ],
            constraints=PropertyConstraints(default="left"),
            category="Appearance",
        ),
    ]


class WidgetRegistry:
    """Central registry for widget metadata."""

    def __init__(self):
        self._metadata: dict[str, WidgetMetadata] = {}
        self._initialize_metadata()

    def _initialize_metadata(self):
        """Initialize all widget metadata."""

        # TEXT
        self._metadata["text"] = WidgetMetadata(
            type="text",
            name="Text",
            description="Static text label",
            category=WidgetCategory.TEXT,
            icon="T",
            default_width=150,
            default_height=30,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="value",
                    label="Text Content",
                    type=PropertyType.STRING,
                    constraints=PropertyConstraints(required=True, default="Text"),
                    category="Content",
                ),
            ]
            + _common_text_props()
            + [
                PropertyDefinition(
                    name="direction",
                    label="Direction",
                    type=PropertyType.SELECT,
                    options=[
                        SelectOption(value="ltr", label="Left to Right"),
                        SelectOption(value="ttb", label="Top to Bottom"),
                    ],
                    constraints=PropertyConstraints(default="ltr"),
                    category="Appearance",
                ),
            ],
        )

        # METRIC
        self._metadata["metric"] = WidgetMetadata(
            type="metric",
            name="Metric Value",
            description="Display a telemetry value (speed, altitude, etc.)",
            category=WidgetCategory.METRICS,
            icon="M",
            default_width=120,
            default_height=40,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(required=True, default="speed"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="kph"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="dp",
                    label="Decimal Places",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0, max=5, default=1),
                    category="Data",
                ),
            ]
            + _common_text_props(),
        )

        # METRIC_UNIT
        self._metadata["metric_unit"] = WidgetMetadata(
            type="metric_unit",
            name="Metric Unit Label",
            description="Display the unit label for a metric",
            category=WidgetCategory.METRICS,
            icon="U",
            default_width=60,
            default_height=20,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(required=True, default="speed"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="kph"),
                    category="Data",
                ),
            ]
            + _common_text_props(),
        )

        # DATETIME
        self._metadata["datetime"] = WidgetMetadata(
            type="datetime",
            name="Date/Time",
            description="Display date and time from video",
            category=WidgetCategory.TEXT,
            icon="D",
            default_width=200,
            default_height=30,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="format",
                    label="Format",
                    type=PropertyType.STRING,
                    description="strftime format string",
                    constraints=PropertyConstraints(required=True, default="%Y-%m-%d %H:%M:%S"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="truncate",
                    label="Truncate",
                    type=PropertyType.NUMBER,
                    description="Characters to remove from end",
                    constraints=PropertyConstraints(min=0, default=0),
                    category="Data",
                ),
            ]
            + _common_text_props(),
        )

        # ICON
        self._metadata["icon"] = WidgetMetadata(
            type="icon",
            name="Icon",
            description="Display an image icon",
            category=WidgetCategory.TEXT,
            icon="I",
            default_width=64,
            default_height=64,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="file",
                    label="Icon File",
                    type=PropertyType.STRING,
                    constraints=PropertyConstraints(required=True, default="default.png"),
                    category="Content",
                ),
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=8, max=512, default=64),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="invert",
                    label="Invert Colors",
                    type=PropertyType.BOOLEAN,
                    constraints=PropertyConstraints(default=True),
                    category="Appearance",
                ),
            ],
        )

        # MOVING_MAP
        self._metadata["moving_map"] = WidgetMetadata(
            type="moving_map",
            name="Moving Map",
            description="Map that follows current location",
            category=WidgetCategory.MAPS,
            icon="MAP",
            default_width=256,
            default_height=256,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Map Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=64, max=1024, default=256),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="zoom",
                    label="Zoom Level",
                    type=PropertyType.NUMBER,
                    description="1-5: Continents/countries\n10-12: Cities\n14-16: Streets\n17-18: Building details\n19: Maximum detail",
                    constraints=PropertyConstraints(min=1, max=19, default=16),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="corner_radius",
                    label="Corner Radius",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0, max=128, default=0),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="opacity",
                    label="Opacity",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0.0, max=1.0, step=0.1, default=0.7),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="rotate",
                    label="Rotate Map",
                    type=PropertyType.BOOLEAN,
                    constraints=PropertyConstraints(default=True),
                    category="Behavior",
                ),
            ],
        )

        # JOURNEY_MAP
        self._metadata["journey_map"] = WidgetMetadata(
            type="journey_map",
            name="Journey Map",
            description="Map showing the entire route",
            category=WidgetCategory.MAPS,
            icon="JM",
            default_width=256,
            default_height=256,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Map Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=64, max=1024, default=256),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="corner_radius",
                    label="Corner Radius",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0, max=128, default=0),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="opacity",
                    label="Opacity",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0.0, max=1.0, step=0.1, default=0.7),
                    category="Appearance",
                ),
            ],
        )

        # MOVING_JOURNEY_MAP
        self._metadata["moving_journey_map"] = WidgetMetadata(
            type="moving_journey_map",
            name="Moving Journey Map",
            description="Combined moving and journey map",
            category=WidgetCategory.MAPS,
            icon="MJM",
            default_width=256,
            default_height=256,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Map Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=64, max=1024, default=256),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="zoom",
                    label="Zoom Level",
                    type=PropertyType.NUMBER,
                    description="1-5: Continents/countries\n10-12: Cities\n14-16: Streets\n17-18: Building details\n19: Maximum detail",
                    constraints=PropertyConstraints(min=1, max=19, default=16),
                    category="Appearance",
                ),
            ],
        )

        # CIRCUIT_MAP
        self._metadata["circuit_map"] = WidgetMetadata(
            type="circuit_map",
            name="Circuit Map",
            description="Map showing circuit/track layout",
            category=WidgetCategory.MAPS,
            icon="CM",
            default_width=256,
            default_height=256,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Map Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=64, max=1024, default=256),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="fill",
                    label="Fill Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,0,0"),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="outline",
                    label="Outline Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,255,255"),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="fill_width",
                    label="Fill Width",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=1, max=20, default=4),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="outline_width",
                    label="Outline Width",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0, max=20, default=0),
                    category="Appearance",
                ),
            ],
        )

        # COMPASS
        self._metadata["compass"] = WidgetMetadata(
            type="compass",
            name="Compass",
            description="Compass with direction indicator",
            category=WidgetCategory.GAUGES,
            icon="C",
            default_width=256,
            default_height=256,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=64, max=512, default=256),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="textsize",
                    label="Text Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=8, max=100, default=16),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="fg",
                    label="Foreground Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,255,255"),
                    category="Appearance",
                ),
                PropertyDefinition(name="bg", label="Background Color", type=PropertyType.COLOR, category="Appearance"),
                PropertyDefinition(
                    name="text",
                    label="Text Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,255,255"),
                    category="Appearance",
                ),
            ],
        )

        # COMPASS_ARROW
        self._metadata["compass_arrow"] = WidgetMetadata(
            type="compass_arrow",
            name="Compass Arrow",
            description="Simple arrow compass",
            category=WidgetCategory.GAUGES,
            icon="CA",
            default_width=256,
            default_height=256,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=64, max=512, default=256),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="textsize",
                    label="Text Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=8, max=100, default=32),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="arrow",
                    label="Arrow Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,255,255"),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="bg",
                    label="Background Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="0,0,0,0"),
                    category="Appearance",
                ),
            ],
        )

        # BAR
        self._metadata["bar"] = WidgetMetadata(
            type="bar",
            name="Bar Indicator",
            description="Horizontal bar for metrics (acceleration, etc.)",
            category=WidgetCategory.GAUGES,
            icon="B",
            default_width=400,
            default_height=30,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="width",
                    label="Width",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=50, max=1000, default=400),
                    category="Size",
                ),
                PropertyDefinition(
                    name="height",
                    label="Height",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=10, max=200, default=30),
                    category="Size",
                ),
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(required=True, default="accel"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="G"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="min",
                    label="Min Value",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=-20),
                    category="Data",
                ),
                PropertyDefinition(
                    name="max",
                    label="Max Value",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=20),
                    category="Data",
                ),
                PropertyDefinition(
                    name="fill",
                    label="Fill Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,255,255,0"),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="bar",
                    label="Bar Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,255,255"),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="outline",
                    label="Outline Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,255,255"),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="cr",
                    label="Corner Radius",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0, max=50, default=5),
                    category="Appearance",
                ),
            ],
        )

        # ZONE_BAR
        self._metadata["zone_bar"] = WidgetMetadata(
            type="zone_bar",
            name="Zone Bar",
            description="Gradient bar with zones (HR zones, etc.)",
            category=WidgetCategory.GAUGES,
            icon="ZB",
            default_width=400,
            default_height=30,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="width",
                    label="Width",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=50, max=1000, default=400),
                    category="Size",
                ),
                PropertyDefinition(
                    name="height",
                    label="Height",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=10, max=200, default=30),
                    category="Size",
                ),
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(required=True, default="hr"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="min",
                    label="Min Value",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=0),
                    category="Data",
                ),
                PropertyDefinition(
                    name="max",
                    label="Max Value",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=400),
                    category="Data",
                ),
                PropertyDefinition(
                    name="z1",
                    label="Zone 1 Threshold",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=120),
                    category="Zones",
                ),
                PropertyDefinition(
                    name="z2",
                    label="Zone 2 Threshold",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=160),
                    category="Zones",
                ),
                PropertyDefinition(
                    name="z3",
                    label="Zone 3 Threshold",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=200),
                    category="Zones",
                ),
                PropertyDefinition(
                    name="z0-rgb",
                    label="Zone 0 Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,255,255"),
                    category="Zones",
                ),
                PropertyDefinition(
                    name="z1-rgb",
                    label="Zone 1 Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="67,235,52"),
                    category="Zones",
                ),
                PropertyDefinition(
                    name="z2-rgb",
                    label="Zone 2 Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="240,232,19"),
                    category="Zones",
                ),
                PropertyDefinition(
                    name="z3-rgb",
                    label="Zone 3 Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="207,19,2"),
                    category="Zones",
                ),
            ],
        )

        # CHART
        self._metadata["chart"] = WidgetMetadata(
            type="chart",
            name="Chart",
            description="Time-series chart for a metric",
            category=WidgetCategory.CHARTS,
            icon="CH",
            default_width=256,
            default_height=64,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(default="alt"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="metres"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="seconds",
                    label="Time Window (seconds)",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=10, max=3600, default=300),
                    category="Data",
                ),
                PropertyDefinition(
                    name="samples",
                    label="Samples",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=10, max=1000, default=256),
                    category="Data",
                ),
                PropertyDefinition(
                    name="height",
                    label="Height",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=20, max=500, default=64),
                    category="Size",
                ),
                PropertyDefinition(
                    name="textsize",
                    label="Text Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=8, max=50, default=16),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="filled",
                    label="Filled",
                    type=PropertyType.BOOLEAN,
                    constraints=PropertyConstraints(default=True),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="values",
                    label="Show Values",
                    type=PropertyType.BOOLEAN,
                    constraints=PropertyConstraints(default=True),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="bg",
                    label="Background Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="0,0,0,170"),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="fill",
                    label="Fill Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="91,113,146,170"),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="line",
                    label="Line Color",
                    type=PropertyType.COLOR,
                    constraints=PropertyConstraints(default="255,255,255,170"),
                    category="Appearance",
                ),
            ],
        )

        # ASI (Airspeed Indicator)
        self._metadata["asi"] = WidgetMetadata(
            type="asi",
            name="Airspeed Indicator",
            description="Aviation-style airspeed indicator",
            category=WidgetCategory.GAUGES,
            icon="ASI",
            default_width=256,
            default_height=256,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=64, max=512, default=256),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(default="speed"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="knots"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="vs0",
                    label="Vs0",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=40),
                    category="Speeds",
                ),
                PropertyDefinition(
                    name="vs",
                    label="Vs",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=46),
                    category="Speeds",
                ),
                PropertyDefinition(
                    name="vfe",
                    label="Vfe",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=103),
                    category="Speeds",
                ),
                PropertyDefinition(
                    name="vno",
                    label="Vno",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=126),
                    category="Speeds",
                ),
                PropertyDefinition(
                    name="vne",
                    label="Vne",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=180),
                    category="Speeds",
                ),
            ],
        )

        # MSI (Motor Speed Indicator)
        self._metadata["msi"] = WidgetMetadata(
            type="msi",
            name="Motor Speed Indicator",
            description="Motor/speedometer style gauge",
            category=WidgetCategory.GAUGES,
            icon="MSI",
            default_width=256,
            default_height=256,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=64, max=512, default=256),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(default="speed"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="kph"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="textsize",
                    label="Text Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=8, max=100, default=16),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="needle",
                    label="Show Needle",
                    type=PropertyType.BOOLEAN,
                    constraints=PropertyConstraints(default=True),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="green",
                    label="Green Zone Start",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=0),
                    category="Zones",
                ),
                PropertyDefinition(
                    name="yellow",
                    label="Yellow Zone Start",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=130),
                    category="Zones",
                ),
                PropertyDefinition(
                    name="end",
                    label="Scale End",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=180),
                    category="Zones",
                ),
            ],
        )

        # GPS_LOCK_ICON
        self._metadata["gps_lock_icon"] = WidgetMetadata(
            type="gps_lock_icon",
            name="GPS Lock Icon",
            description="Icon showing GPS signal status",
            category=WidgetCategory.INDICATORS,
            icon="GPS",
            default_width=64,
            default_height=64,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=16, max=256, default=64),
                    category="Appearance",
                ),
            ],
        )

        # COMPOSITE (Container)
        self._metadata["composite"] = WidgetMetadata(
            type="composite",
            name="Composite",
            description="Container for grouping widgets",
            category=WidgetCategory.CONTAINERS,
            icon="[]",
            default_width=200,
            default_height=100,
            is_container=True,
            properties=_common_position_props(),
        )

        # TRANSLATE (Container with offset)
        self._metadata["translate"] = WidgetMetadata(
            type="translate",
            name="Translate",
            description="Container with position offset",
            category=WidgetCategory.CONTAINERS,
            icon="->",
            default_width=200,
            default_height=100,
            is_container=True,
            properties=_common_position_props(),
        )

        # FRAME (Container with styling)
        self._metadata["frame"] = WidgetMetadata(
            type="frame",
            name="Frame",
            description="Styled container with background",
            category=WidgetCategory.CONTAINERS,
            icon="[F]",
            default_width=300,
            default_height=200,
            is_container=True,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="width",
                    label="Width",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=10, required=True, default=300),
                    category="Size",
                ),
                PropertyDefinition(
                    name="height",
                    label="Height",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=10, required=True, default=200),
                    category="Size",
                ),
                PropertyDefinition(name="bg", label="Background Color", type=PropertyType.COLOR, category="Appearance"),
                PropertyDefinition(
                    name="outline", label="Outline Color", type=PropertyType.COLOR, category="Appearance"
                ),
                PropertyDefinition(
                    name="cr",
                    label="Corner Radius",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0, max=100, default=0),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="opacity",
                    label="Opacity",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0.0, max=1.0, step=0.1, default=1.0),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="fo",
                    label="Fade Out",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=0, max=100, default=0),
                    category="Appearance",
                ),
            ],
        )

        # CAIRO WIDGETS
        self._metadata["cairo_circuit_map"] = WidgetMetadata(
            type="cairo_circuit_map",
            name="Cairo Circuit Map",
            description="Advanced circuit map (requires Cairo)",
            category=WidgetCategory.CAIRO,
            icon="CCM",
            default_width=256,
            default_height=256,
            requires_cairo=True,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=64, max=1024, default=256),
                    category="Appearance",
                ),
            ],
        )

        self._metadata["cairo_gauge_marker"] = WidgetMetadata(
            type="cairo_gauge_marker",
            name="Cairo Gauge Marker",
            description="Arc gauge with marker (requires Cairo)",
            category=WidgetCategory.CAIRO,
            icon="CGM",
            default_width=300,
            default_height=300,
            requires_cairo=True,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(required=True, default="speed"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="kph"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=100, max=800, default=300),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="start",
                    label="Start Angle",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=0),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="length",
                    label="Arc Length",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=270),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="max",
                    label="Max Value",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=200),
                    category="Data",
                ),
            ],
        )

        self._metadata["cairo_gauge_round_annotated"] = WidgetMetadata(
            type="cairo_gauge_round_annotated",
            name="Cairo Round Annotated Gauge",
            description="Circular gauge with annotations (requires Cairo)",
            category=WidgetCategory.CAIRO,
            icon="CGRA",
            default_width=300,
            default_height=300,
            requires_cairo=True,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(required=True, default="speed"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="kph"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=100, max=800, default=300),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="start",
                    label="Start Angle",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=90),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="length",
                    label="Arc Length",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=270),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="max",
                    label="Max Value",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=200),
                    category="Data",
                ),
            ],
        )

        self._metadata["cairo_gauge_arc_annotated"] = WidgetMetadata(
            type="cairo_gauge_arc_annotated",
            name="Cairo Arc Annotated Gauge",
            description="Arc gauge with annotations (requires Cairo)",
            category=WidgetCategory.CAIRO,
            icon="CGAA",
            default_width=300,
            default_height=150,
            requires_cairo=True,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(required=True, default="speed"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="kph"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=100, max=800, default=300),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="start",
                    label="Start Angle",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=0),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="length",
                    label="Arc Length",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=180),
                    category="Appearance",
                ),
            ],
        )

        self._metadata["cairo_gauge_donut"] = WidgetMetadata(
            type="cairo_gauge_donut",
            name="Cairo Donut Gauge",
            description="Donut/ring gauge (requires Cairo)",
            category=WidgetCategory.CAIRO,
            icon="CGD",
            default_width=300,
            default_height=300,
            requires_cairo=True,
            properties=_common_position_props()
            + [
                PropertyDefinition(
                    name="metric",
                    label="Metric",
                    type=PropertyType.METRIC,
                    options=AVAILABLE_METRICS,
                    constraints=PropertyConstraints(required=True, default="speed"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="units",
                    label="Units",
                    type=PropertyType.UNITS,
                    options=AVAILABLE_UNITS,
                    constraints=PropertyConstraints(default="kph"),
                    category="Data",
                ),
                PropertyDefinition(
                    name="size",
                    label="Size",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(min=100, max=800, default=300),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="start",
                    label="Start Angle",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=0),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="length",
                    label="Arc Length",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=360),
                    category="Appearance",
                ),
                PropertyDefinition(
                    name="max",
                    label="Max Value",
                    type=PropertyType.NUMBER,
                    constraints=PropertyConstraints(default=200),
                    category="Data",
                ),
            ],
        )

    def get_metadata(self, widget_type: str) -> WidgetMetadata | None:
        """Get metadata for a specific widget type."""
        return self._metadata.get(widget_type)

    def get_all_metadata(self) -> list[WidgetMetadata]:
        """Get all widget metadata."""
        return list(self._metadata.values())

    def get_categories(self) -> list[str]:
        """Get all widget categories."""
        return [cat.value for cat in WidgetCategory]


# Singleton instance
widget_registry = WidgetRegistry()
