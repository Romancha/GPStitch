"""GPX decoding must not depend on the operating system's text encoding."""

import gzip
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.fixtures.data import SAMPLE_GPX_CONTENT


@pytest.fixture(params=["utf-8", "utf-8-sig"])
def unicode_gpx_file(tmp_path, monkeypatch, request):
    """Simulate a Windows GBK default while retaining real file reads and parsing."""
    path = tmp_path / "跑.gpx"
    content = SAMPLE_GPX_CONTENT.replace("Test Track", "跑").replace("12:00:01Z", "12:00:02Z")
    path.write_bytes(content.encode(request.param))
    original_open = Path.open

    def open_with_gbk_default(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        if self == path and "b" not in mode and encoding is None:
            encoding = "gbk"
        return original_open(self, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", open_with_gbk_default)
    return path


@pytest.mark.parametrize("reader", ["metadata", "preview", "dashboard"])
def test_gpx_readers_ignore_system_encoding(unicode_gpx_file, reader):
    from gopro_overlay.loading import load_external
    from gopro_overlay.units import units

    from gpstitch.services.metadata import extract_gpx_fit_metadata
    from gpstitch.services.renderer import _load_external_timeseries

    if reader == "metadata":
        metadata = extract_gpx_fit_metadata(unicode_gpx_file)
        assert metadata is not None
        assert metadata.gps_point_count == 2
        assert metadata.duration_seconds == 2
        return

    loader = _load_external_timeseries if reader == "preview" else load_external
    timeseries = loader(unicode_gpx_file, units)
    assert len(timeseries) == 2
    assert timeseries.min == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert timeseries.max == datetime(2024, 1, 1, 12, 0, 2, tzinfo=UTC)
    point = timeseries.get(timeseries.min)
    assert point.point.lat == pytest.approx(55.7558)
    assert point.point.lon == pytest.approx(37.6173)
    assert point.alt.magnitude == 150


def test_gzip_gpx_loading_is_preserved(tmp_path):
    from gopro_overlay import gpx
    from gopro_overlay.units import units

    path = tmp_path / "track.gpx.gz"
    path.write_bytes(gzip.compress(SAMPLE_GPX_CONTENT.encode("utf-8-sig")))

    points = gpx.load(path, units)

    assert len(points) == 2
    assert points[0].lat == pytest.approx(55.7558)
    assert points[0].time == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_gpx_encoding_patch_is_idempotent():
    from gopro_overlay import gpx

    from gpstitch.patches.gpx_patches import patch_gpx_encoding

    patch_gpx_encoding()
    loader = gpx.load
    patch_gpx_encoding()

    assert gpx.load is loader
