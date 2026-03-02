"""Centralized constants for the telemetry_studio application.

All unit options, defaults, and other shared constants should be defined here.
Values match gopro-dashboard CLI arguments which are then passed to pint.
"""

# =============================================================================
# UNIT DEFAULTS
# =============================================================================

DEFAULT_UNITS_SPEED = "kph"
DEFAULT_UNITS_ALTITUDE = "metre"
DEFAULT_UNITS_DISTANCE = "km"
DEFAULT_UNITS_TEMPERATURE = "degC"
DEFAULT_MAP_STYLE = "osm"

# =============================================================================
# UNIT OPTIONS
# =============================================================================

UNIT_OPTIONS = {
    "speed": {
        "label": "Speed",
        "options": [
            {"value": "kph", "label": "km/h"},
            {"value": "mph", "label": "mph"},
            {"value": "mps", "label": "m/s"},
            {"value": "knot", "label": "knots"},
        ],
        "default": DEFAULT_UNITS_SPEED,
    },
    "altitude": {
        "label": "Altitude",
        "options": [
            {"value": "metre", "label": "Meters"},
            {"value": "foot", "label": "Feet"},
        ],
        "default": DEFAULT_UNITS_ALTITUDE,
    },
    "distance": {
        "label": "Distance",
        "options": [
            {"value": "km", "label": "Kilometers"},
            {"value": "mile", "label": "Miles"},
            {"value": "foot", "label": "Feet"},
            {"value": "nmi", "label": "Nautical Miles"},
        ],
        "default": DEFAULT_UNITS_DISTANCE,
    },
    "temperature": {
        "label": "Temperature",
        "options": [
            {"value": "degC", "label": "Celsius"},
            {"value": "degF", "label": "Fahrenheit"},
            {"value": "kelvin", "label": "Kelvin"},
        ],
        "default": DEFAULT_UNITS_TEMPERATURE,
    },
}

# =============================================================================
# GPX/FIT OPTIONS
# =============================================================================

DEFAULT_GPX_MERGE_MODE = "OVERWRITE"

# =============================================================================
# GPS FILTER DEFAULTS
# =============================================================================
# DOP max matches gopro-dashboard CLI default (10)
# Speed max is higher than CLI default (60) to support motorcycles/cars

DEFAULT_GPS_DOP_MAX = 10.0  # GPS dilution of precision max
DEFAULT_GPS_SPEED_MAX = 200.0  # Max speed in kph to filter outliers
DEFAULT_GPS_TARGET_HZ = 1  # Target GPS sampling rate in Hz (1 = 1 point/sec)

# =============================================================================
# GPS QUALITY THRESHOLDS
# =============================================================================
# Based on GPS accuracy best practices:
# https://gisgeography.com/gps-accuracy-hdop-pdop-gdop-multipath/

DOP_THRESHOLD_EXCELLENT = 2.0  # DOP < 2: Ideal for precise tracking
DOP_THRESHOLD_GOOD = 5.0  # DOP 2-5: Suitable for most applications
DOP_THRESHOLD_MODERATE = 10.0  # DOP 5-10: Acceptable, some accuracy loss
# DOP > 10: Poor/unreliable positioning
# DOP = 99.99: No GPS signal (GoPro default when no lock)

GPS_QUALITY_SCORES = ("excellent", "good", "ok", "poor", "no_signal")
