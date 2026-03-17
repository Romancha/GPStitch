"""Test data constants and sample data."""

from pathlib import Path

# Sample XML layout for testing XML converter
SAMPLE_LAYOUT_XML = """<layout>
  <component type="text" x="100" y="50" size="32" rgb="255,255,255">Speed</component>
  <component type="metric" x="100" y="100" metric="speed" units="kph" dp="1" />
</layout>"""

SAMPLE_LAYOUT_XML_WITH_CONTAINERS = """<layout>
  <composite x="50" y="50">
    <component type="text" x="0" y="0">Group 1</component>
    <component type="metric" x="0" y="40" metric="alt" units="metre" />
  </composite>
  <translate x="200" y="200">
    <component type="compass" size="128" />
  </translate>
</layout>"""

SAMPLE_LAYOUT_XML_MINIMAL = """<layout>
  <component type="text" x="0" y="0">Minimal</component>
</layout>"""

# Sample GPX content
SAMPLE_GPX_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Test">
  <trk>
    <name>Test Track</name>
    <trkseg>
      <trkpt lat="55.7558" lon="37.6173">
        <ele>150</ele>
        <time>2024-01-01T12:00:00Z</time>
      </trkpt>
      <trkpt lat="55.7560" lon="37.6175">
        <ele>151</ele>
        <time>2024-01-01T12:00:01Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>"""

# Test video paths (included in repo)
TEST_VIDEO_PATH = str(Path(__file__).parent / "videos" / "raw_gopro_with_telemetry.MP4")
TEST_VIDEO_PATH_2 = str(Path(__file__).parent / "videos" / "raw_gopro_with_telemetry_2.MP4")
TEST_MOV_VIDEO_PATH = str(Path(__file__).parent / "videos" / "IMG_2927.MOV")
TEST_RUN_GPX_PATH = str(Path(__file__).parent / "videos" / "hiking_activity.gpx")
TEST_DJI_VIDEO_PATH = str(Path(__file__).parent / "videos" / "DJI_20250723102139_0001_D.MP4")
TEST_DJI_SRT_PATH = str(Path(__file__).parent / "videos" / "DJI_20250723102139_0001_D.SRT")
TEST_DJI_ACTION_VIDEO_PATH = str(Path(__file__).parent / "videos" / "DJI_20260315180109_0003_D_5s_fixture.MP4")

# Allowed extensions for upload
ALLOWED_VIDEO_EXTENSIONS = [".mp4", ".MP4", ".mov", ".MOV"]
ALLOWED_GPX_FIT_EXTENSIONS = [".gpx", ".GPX", ".fit", ".FIT"]
