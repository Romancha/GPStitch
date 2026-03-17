"""Unit tests for DJI meta protobuf parser."""

import struct
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from gopro_overlay.gpmf import GPSFix

from gpstitch.services.dji_meta_parser import (
    DjiMetaPoint,
    _decode_double,
    _decode_field,
    _decode_float,
    _decode_varint,
    _get_double,
    _get_float,
    _get_string,
    _get_submessage,
    _get_varint,
    _iter_fields,
    _parse_gps_from_sample,
    detect_dji_meta_stream,
    dji_meta_to_gpx_file,
    dji_meta_to_timeseries,
    parse_dji_meta,
)

# --- Raw protobuf test data ---

# First sample from fixture: DJI_20260315180109_0003_D_5s_fixture.MP4
# Contains GPS: lat=50.89076500000001, lon=6.6743936, alt=122745mm, timestamp="2026-03-15 23:58:14"
# velocity: vx=-1.5, vy=10.5
SAMPLE_0_HEX = (
    "1acd010a0b08ad551085d7f0fe1e180112631a050d0000c84322050a030196062a05"
    "0d0000803f320308822f3a0042004a140d3045793f1524f04f3d1d89b231be254cde"
    "0dbe520f159ed17fbe1d2c6de33e255b8ac6bf5a050d000000c062050d000000c06a"
    "0610c10518ec0772060a04b45be80722590a14080110012209444a4920414330303"
    "42d0000c84112350a14080111f3b567960472494019de86623c94b21a4010f9be07"
    "2001280132150a13323032362d30332d31352032333a35383a31341a0a0d0000c0bf"
    "1500002841"
)
SAMPLE_0_BYTES = bytes.fromhex(SAMPLE_0_HEX)


class TestDecodeVarint:
    def test_single_byte(self):
        # varint 1 = 0x01
        val, pos = _decode_varint(b"\x01", 0)
        assert val == 1
        assert pos == 1

    def test_multi_byte(self):
        # varint 300 = 0xAC 0x02
        val, pos = _decode_varint(b"\xac\x02", 0)
        assert val == 300
        assert pos == 2

    def test_with_offset(self):
        val, pos = _decode_varint(b"\x00\xac\x02", 1)
        assert val == 300
        assert pos == 3

    def test_zero(self):
        val, pos = _decode_varint(b"\x00", 0)
        assert val == 0
        assert pos == 1

    def test_large_value(self):
        # Encode a larger number: 10925 = field 1 varint in our fixture
        val, pos = _decode_varint(b"\xad\x55", 0)
        assert val == 10925
        assert pos == 2


class TestDecodeField:
    def test_varint_field(self):
        # field 1, wire type 0 (varint), value 150
        data = b"\x08\x96\x01"
        fn, wt, val, pos = _decode_field(data, 0)
        assert fn == 1
        assert wt == 0
        assert val == 150
        assert pos == 3

    def test_fixed64_field(self):
        # field 2, wire type 1 (64-bit), 8 bytes of data
        tag = (2 << 3) | 1  # = 0x11
        payload = struct.pack("<d", 50.89076500000001)
        data = bytes([tag]) + payload
        fn, wt, val, pos = _decode_field(data, 0)
        assert fn == 2
        assert wt == 1
        assert len(val) == 8
        assert struct.unpack("<d", val)[0] == pytest.approx(50.89076500000001)

    def test_length_delimited_field(self):
        # field 4, wire type 2, string "test"
        tag = (4 << 3) | 2  # = 0x22
        content = b"test"
        data = bytes([tag, len(content)]) + content
        fn, wt, val, pos = _decode_field(data, 0)
        assert fn == 4
        assert wt == 2
        assert val == b"test"
        assert pos == 6

    def test_fixed32_field(self):
        # field 1, wire type 5, float 25.0
        tag = (1 << 3) | 5  # = 0x0d
        payload = struct.pack("<f", 25.0)
        data = bytes([tag]) + payload
        fn, wt, val, pos = _decode_field(data, 0)
        assert fn == 1
        assert wt == 5
        assert len(val) == 4
        assert struct.unpack("<f", val)[0] == pytest.approx(25.0)

    def test_empty_data(self):
        fn, wt, val, pos = _decode_field(b"", 0)
        assert fn is None

    def test_truncated_fixed64(self):
        # field 2, wire type 1, but only 3 bytes of data
        data = bytes([(2 << 3) | 1]) + b"\x00\x00\x00"
        fn, wt, val, pos = _decode_field(data, 0)
        assert fn is None


class TestDecodeHelpers:
    def test_decode_double(self):
        data = struct.pack("<d", 50.89076500000001)
        assert _decode_double(data) == pytest.approx(50.89076500000001)

    def test_decode_float(self):
        data = struct.pack("<f", 25.0)
        assert _decode_float(data) == pytest.approx(25.0)


class TestFieldAccessors:
    def _make_varint_field(self, field_num, value):
        """Build a protobuf varint field."""
        tag = (field_num << 3) | 0
        parts = []
        v = value
        while v > 0x7F:
            parts.append((v & 0x7F) | 0x80)
            v >>= 7
        parts.append(v)
        return bytes([tag] + parts)

    def _make_submessage(self, field_num, content):
        """Build a length-delimited field."""
        tag_byte = (field_num << 3) | 2
        length = len(content)
        # Encode length as varint
        length_bytes = []
        v = length
        while v > 0x7F:
            length_bytes.append((v & 0x7F) | 0x80)
            v >>= 7
        length_bytes.append(v)
        return bytes([tag_byte] + length_bytes) + content

    def test_iter_fields(self):
        data = self._make_varint_field(1, 42) + self._make_varint_field(2, 99)
        fields = list(_iter_fields(data))
        assert len(fields) == 2
        assert fields[0] == (1, 0, 42)
        assert fields[1] == (2, 0, 99)

    def test_get_submessage(self):
        inner = b"hello"
        data = self._make_submessage(5, inner) + self._make_varint_field(1, 0)
        result = _get_submessage(data, 5)
        assert result == inner

    def test_get_submessage_missing(self):
        data = self._make_varint_field(1, 42)
        assert _get_submessage(data, 5) is None

    def test_get_varint(self):
        data = self._make_varint_field(3, 12345)
        assert _get_varint(data, 3) == 12345

    def test_get_varint_missing(self):
        data = self._make_varint_field(1, 42)
        assert _get_varint(data, 9) is None

    def test_get_double(self):
        tag = (2 << 3) | 1
        payload = struct.pack("<d", 3.14)
        data = bytes([tag]) + payload
        assert _get_double(data, 2) == pytest.approx(3.14)

    def test_get_float(self):
        tag = (1 << 3) | 5
        payload = struct.pack("<f", 2.5)
        data = bytes([tag]) + payload
        assert _get_float(data, 1) == pytest.approx(2.5)

    def test_get_string(self):
        data = self._make_submessage(4, b"DJI AC004")
        assert _get_string(data, 4) == "DJI AC004"

    def test_get_string_missing(self):
        data = self._make_varint_field(1, 0)
        assert _get_string(data, 4) is None


class TestParseGpsFromSample:
    """Test GPS extraction from real protobuf sample data."""

    def test_parse_first_sample(self):
        """Parse the first sample from the fixture - should extract valid GPS."""
        # Strip the outer field 3 wrapper to get inner sample data
        fn, wt, inner, _ = _decode_field(SAMPLE_0_BYTES, 0)
        assert fn == 3
        assert wt == 2

        point = _parse_gps_from_sample(inner, 0)
        assert point is not None
        assert point.frame_idx == 0
        assert point.lat == pytest.approx(50.8907650, abs=1e-5)
        assert point.lon == pytest.approx(6.6743936, abs=1e-5)
        assert point.alt_m == pytest.approx(122.745, abs=0.001)
        assert point.timestamp == datetime(2026, 3, 15, 23, 58, 14)
        assert point.velocity_2d[0] == pytest.approx(-1.5, abs=0.1)
        assert point.velocity_2d[1] == pytest.approx(10.5, abs=0.1)

    def test_no_gps_field(self):
        """Sample without field 4 (GPS) should return None."""
        # Build a minimal sample with only f1 (frame info)
        tag = (1 << 3) | 2  # field 1, length-delimited
        inner = bytes([tag, 2, 0x08, 0x01])  # f1 with varint 1
        assert _parse_gps_from_sample(inner, 0) is None

    def test_no_fix(self):
        """Sample with GPS fix type 0 should return None."""
        # Build GPS data with fix=0
        # coords msg: f1=0 (no fix), f2=lat, f3=lon
        coords = bytes([(1 << 3) | 0, 0])  # f1 varint = 0
        coords += bytes([(2 << 3) | 1]) + struct.pack("<d", 50.0)  # f2 double
        coords += bytes([(3 << 3) | 1]) + struct.pack("<d", 6.0)  # f3 double

        fix_msg = bytes([(1 << 3) | 2, len(coords)]) + coords
        gps_msg = bytes([(2 << 3) | 2, len(fix_msg)]) + fix_msg
        sample = bytes([(4 << 3) | 2, len(gps_msg)]) + gps_msg

        assert _parse_gps_from_sample(sample, 0) is None

    def test_zero_coordinates(self):
        """Sample with lat=0, lon=0 should return None."""
        coords = bytes([(1 << 3) | 0, 1])  # f1 varint = 1 (fix)
        coords += bytes([(2 << 3) | 1]) + struct.pack("<d", 0.0)  # lat=0
        coords += bytes([(3 << 3) | 1]) + struct.pack("<d", 0.0)  # lon=0

        ts_str = b"2026-03-15 23:58:14"
        ts_inner = bytes([(1 << 3) | 2, len(ts_str)]) + ts_str
        ts_msg = bytes([(6 << 3) | 2, len(ts_inner)]) + ts_inner

        fix_msg = bytes([(1 << 3) | 2, len(coords)]) + coords
        fix_msg += bytes([(2 << 3) | 0, 100])  # alt
        fix_msg += ts_msg

        gps_msg = bytes([(2 << 3) | 2, len(fix_msg)]) + fix_msg
        sample = bytes([(4 << 3) | 2, len(gps_msg)]) + gps_msg

        assert _parse_gps_from_sample(sample, 0) is None


class TestParseDjiMeta:
    """Test parsing of concatenated protobuf samples."""

    def test_parse_single_sample(self):
        """Parse raw bytes containing a single sample."""
        points = parse_dji_meta(SAMPLE_0_BYTES)
        assert len(points) == 1
        assert points[0].lat == pytest.approx(50.8907650, abs=1e-5)
        assert points[0].lon == pytest.approx(6.6743936, abs=1e-5)

    def test_parse_empty_data(self):
        """Empty data should return empty list."""
        assert parse_dji_meta(b"") == []

    def test_parse_truncated_data(self):
        """Truncated data should not crash, just return what's parseable."""
        points = parse_dji_meta(SAMPLE_0_BYTES[:10])
        assert isinstance(points, list)
        assert len(points) == 0


class TestDetectDjiMetaStream:
    """Test DJI meta stream detection via ffprobe."""

    def test_detect_with_djmd_tag(self):
        """Should detect stream with codec_tag_string=djmd."""
        mock_output = MagicMock()
        # str() is called on stdout in the parser, so provide a string-like value
        mock_output.stdout = '{"streams": [{"index": 0, "codec_type": "video", "codec_tag_string": "avc1", "tags": {}}, {"index": 2, "codec_type": "data", "codec_tag_string": "djmd", "tags": {"handler_name": "DJI meta"}}]}'

        with patch("gpstitch.services.dji_meta_parser.FFMPEG") as mock_ffmpeg:
            mock_ffmpeg.return_value.ffprobe.return_value.invoke.return_value = mock_output
            result = detect_dji_meta_stream(Path("/fake/video.mp4"))
            assert result == 2

    def test_detect_with_handler_name(self):
        """Should detect stream with handler_name=DJI meta even without djmd tag."""
        mock_output = MagicMock()
        mock_output.stdout = '{"streams": [{"index": 0, "codec_type": "video", "codec_tag_string": "avc1", "tags": {}}, {"index": 3, "codec_type": "data", "codec_tag_string": "none", "tags": {"handler_name": "DJI meta"}}]}'

        with patch("gpstitch.services.dji_meta_parser.FFMPEG") as mock_ffmpeg:
            mock_ffmpeg.return_value.ffprobe.return_value.invoke.return_value = mock_output
            result = detect_dji_meta_stream(Path("/fake/video.mp4"))
            assert result == 3

    def test_no_dji_meta_stream(self):
        """Should return None when no DJI meta stream exists."""
        mock_output = MagicMock()
        mock_output.stdout = (
            '{"streams": [{"index": 0, "codec_type": "video", "codec_tag_string": "avc1", "tags": {}}]}'
        )

        with patch("gpstitch.services.dji_meta_parser.FFMPEG") as mock_ffmpeg:
            mock_ffmpeg.return_value.ffprobe.return_value.invoke.return_value = mock_output
            result = detect_dji_meta_stream(Path("/fake/video.mp4"))
            assert result is None

    def test_ffprobe_failure(self):
        """Should return None on ffprobe failure."""
        with patch("gpstitch.services.dji_meta_parser.FFMPEG") as mock_ffmpeg:
            mock_ffmpeg.return_value.ffprobe.return_value.invoke.side_effect = Exception("ffprobe error")
            result = detect_dji_meta_stream(Path("/fake/video.mp4"))
            assert result is None


# --- Helper to build test DjiMetaPoint instances ---


def _make_points(count: int = 5, base_lat: float = 50.890765, base_lon: float = 6.674394) -> list[DjiMetaPoint]:
    """Create a list of DjiMetaPoint for testing."""
    points = []
    for i in range(count):
        points.append(
            DjiMetaPoint(
                frame_idx=i,
                timestamp=datetime(2026, 3, 15, 23, 58, 14 + i),
                lat=base_lat + i * 0.0001,
                lon=base_lon + i * 0.0001,
                alt_m=122.745 + i * 0.1,
                velocity_2d=(3.0, 4.0),  # speed = 5.0 m/s
            )
        )
    return points


class TestDjiMetaToTimeseries:
    """Test conversion of DjiMetaPoint list to Timeseries."""

    def test_creates_timeseries_with_correct_count(self):
        from gopro_overlay.units import units

        points = _make_points(5)
        ts = dji_meta_to_timeseries(points, units)
        assert len(ts) == 5

    def test_creates_timeseries_with_sampling(self):
        from gopro_overlay.units import units

        points = _make_points(10)
        ts = dji_meta_to_timeseries(points, units, sample_rate=5)
        assert len(ts) == 2  # 10 / 5 = 2

    def test_entry_has_correct_gps(self):
        from gopro_overlay.units import units

        points = _make_points(1)
        ts = dji_meta_to_timeseries(points, units)
        entry = ts.items()[0]
        assert entry.point.lat == pytest.approx(50.890765)
        assert entry.point.lon == pytest.approx(6.674394)

    def test_entry_has_altitude(self):
        from gopro_overlay.units import units

        points = _make_points(1)
        ts = dji_meta_to_timeseries(points, units)
        entry = ts.items()[0]
        assert entry.alt.magnitude == pytest.approx(122.745)

    def test_speed_from_velocity(self):
        """Speed should be calculated from 2D velocity vector."""
        from gopro_overlay.units import units

        # vx=3, vy=4 -> speed=5
        points = [
            DjiMetaPoint(
                frame_idx=0,
                timestamp=datetime(2026, 3, 15, 23, 58, 14),
                lat=50.0,
                lon=6.0,
                alt_m=100.0,
                velocity_2d=(3.0, 4.0),
            )
        ]
        ts = dji_meta_to_timeseries(points, units)
        entry = ts.items()[0]
        assert entry.speed.magnitude == pytest.approx(5.0)

    def test_speed_zero_velocity(self):
        """Zero velocity should produce zero speed."""
        from gopro_overlay.units import units

        points = [
            DjiMetaPoint(
                frame_idx=0,
                timestamp=datetime(2026, 3, 15, 23, 58, 14),
                lat=50.0,
                lon=6.0,
                alt_m=100.0,
                velocity_2d=(0.0, 0.0),
            )
        ]
        ts = dji_meta_to_timeseries(points, units)
        entry = ts.items()[0]
        assert entry.speed.magnitude == pytest.approx(0.0)

    def test_entry_has_gps_lock(self):
        from gopro_overlay.units import units

        points = _make_points(1)
        ts = dji_meta_to_timeseries(points, units)
        entry = ts.items()[0]
        assert entry.gpsfix == GPSFix.LOCK_3D.value

    def test_empty_points_returns_empty_timeseries(self):
        from gopro_overlay.units import units

        ts = dji_meta_to_timeseries([], units)
        assert len(ts) == 0


class TestDjiMetaToGpxFile:
    """Test GPX file generation from DjiMetaPoint list."""

    def test_creates_valid_gpx_file(self, tmp_path):
        points = _make_points(3)
        output = tmp_path / "test.gpx"
        result = dji_meta_to_gpx_file(Path("/fake/video.mp4"), output, points=points)
        assert result == output
        assert output.exists()

    def test_gpx_has_correct_structure(self, tmp_path):
        points = _make_points(3)
        output = tmp_path / "test.gpx"
        dji_meta_to_gpx_file(Path("/fake/video.mp4"), output, points=points)

        tree = ET.parse(str(output))
        root = tree.getroot()
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        trkpts = root.findall(".//gpx:trkpt", ns)
        assert len(trkpts) == 3

    def test_gpx_coordinates_match(self, tmp_path):
        points = _make_points(1)
        output = tmp_path / "test.gpx"
        dji_meta_to_gpx_file(Path("/fake/video.mp4"), output, points=points)

        tree = ET.parse(str(output))
        root = tree.getroot()
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        trkpt = root.find(".//gpx:trkpt", ns)
        assert float(trkpt.get("lat")) == pytest.approx(50.890765, abs=1e-5)
        assert float(trkpt.get("lon")) == pytest.approx(6.674394, abs=1e-5)

    def test_gpx_has_elevation(self, tmp_path):
        points = _make_points(1)
        output = tmp_path / "test.gpx"
        dji_meta_to_gpx_file(Path("/fake/video.mp4"), output, points=points)

        tree = ET.parse(str(output))
        root = tree.getroot()
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        ele = root.find(".//gpx:ele", ns)
        assert ele is not None
        assert float(ele.text) == pytest.approx(122.7, abs=0.2)

    def test_gpx_has_time(self, tmp_path):
        points = _make_points(1)
        output = tmp_path / "test.gpx"
        dji_meta_to_gpx_file(Path("/fake/video.mp4"), output, points=points)

        tree = ET.parse(str(output))
        root = tree.getroot()
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        time_el = root.find(".//gpx:time", ns)
        assert time_el is not None
        assert "2026-03-15" in time_el.text

    def test_gpx_with_sample_rate(self, tmp_path):
        points = _make_points(10)
        output = tmp_path / "test.gpx"
        dji_meta_to_gpx_file(Path("/fake/video.mp4"), output, sample_rate=5, points=points)

        tree = ET.parse(str(output))
        root = tree.getroot()
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        trkpts = root.findall(".//gpx:trkpt", ns)
        assert len(trkpts) == 2

    def test_gpx_empty_points_raises(self, tmp_path):
        output = tmp_path / "test.gpx"
        with pytest.raises(ValueError, match="No valid GPS data"):
            dji_meta_to_gpx_file(Path("/fake/video.mp4"), output, points=[])
