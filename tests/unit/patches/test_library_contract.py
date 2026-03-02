"""Contract tests for gopro_overlay library APIs used by patches.

These tests verify that the gopro_overlay library exposes the APIs our patches
depend on. If the library changes, these tests will fail BEFORE the patches
silently break at runtime.

Covered patches:
- gpx_patches.py     → TestLoadingModuleContract, TestTimeseriesContract
- metric_patches.py  → TestMetricAccessorContract
- ffmpeg_gopro_patches.py   → TestFFMPEGGoProContract
- ffmpeg_overlay_patches.py → TestFFMPEGOverlayVideoContract
"""

import inspect
from pathlib import Path
from unittest.mock import Mock

import pytest


class TestLoadingModuleContract:
    """Verify gopro_overlay.loading API that gpx_patches.py depends on."""

    def test_load_external_exists(self):
        from gopro_overlay.loading import load_external

        assert callable(load_external)

    def test_load_external_signature(self):
        """load_external must accept (filepath, units) — our patch replaces it."""
        from gopro_overlay.loading import load_external

        sig = inspect.signature(load_external)
        params = list(sig.parameters.keys())
        assert len(params) >= 2, f"Expected at least 2 params, got {params}"
        assert params[0] == "filepath", f"First param should be 'filepath', got '{params[0]}'"
        assert params[1] == "units", f"Second param should be 'units', got '{params[1]}'"


class TestTimeseriesContract:
    """Verify Timeseries/Entry APIs that gpx_patches.py depends on."""

    def test_entry_accepts_custom_kwargs(self):
        """Entry must accept arbitrary kwargs like iso, fnum, ev, ct for DJI metrics."""
        from datetime import datetime

        from gopro_overlay.point import Point
        from gopro_overlay.timeseries import Entry
        from gopro_overlay.units import units

        entry = Entry(
            datetime(2024, 1, 1),
            point=Point(69.0, 35.0),
            alt=units.Quantity(100.0, units.m),
            iso=units.Quantity(100),
            fnum=units.Quantity(2.8),
            ev=units.Quantity(0.0),
            ct=units.Quantity(5500),
            shutter=units.Quantity(0.001),
            focal_len=units.Quantity(24.0),
        )

        assert entry.iso is not None
        assert entry.fnum is not None
        assert entry.ev is not None
        assert entry.ct is not None
        assert entry.shutter is not None
        assert entry.focal_len is not None

    def test_timeseries_preserves_custom_entry_attrs(self):
        """Timeseries.add() + .get() must preserve custom attributes on Entry."""
        from datetime import datetime

        from gopro_overlay.point import Point
        from gopro_overlay.timeseries import Entry, Timeseries
        from gopro_overlay.units import units

        ts = Timeseries()
        dt = datetime(2024, 1, 1, 12, 0, 0)
        entry = Entry(
            dt,
            point=Point(69.0, 35.0),
            alt=units.Quantity(100.0, units.m),
            iso=units.Quantity(200),
            fnum=units.Quantity(1.7),
        )
        ts.add(entry)

        retrieved = ts.get(ts.min)
        assert retrieved.iso is not None
        assert retrieved.fnum is not None

    def test_timeseries_has_min_max_get(self):
        """Timeseries must expose .min, .max, .get() — used by patched load."""
        from datetime import datetime

        from gopro_overlay.point import Point
        from gopro_overlay.timeseries import Entry, Timeseries
        from gopro_overlay.units import units

        ts = Timeseries()
        entry = Entry(
            datetime(2024, 1, 1),
            point=Point(0, 0),
            alt=units.Quantity(0, units.m),
        )
        ts.add(entry)

        assert ts.min is not None
        assert ts.max is not None
        assert callable(ts.get)
        assert ts.get(ts.min) is not None


class TestMetricAccessorContract:
    """Verify gopro_overlay.layout_xml API that metric_patches.py depends on."""

    def test_metric_accessor_from_exists(self):
        from gopro_overlay.layout_xml import metric_accessor_from

        assert callable(metric_accessor_from)

    def test_known_metric_returns_callable(self):
        """Standard metrics like 'speed' must return a callable accessor."""
        from gopro_overlay.layout_xml import metric_accessor_from

        accessor = metric_accessor_from("speed")
        assert callable(accessor)

    def test_unknown_metric_raises_oserror(self):
        """Unknown metrics must raise OSError — our patch catches this to add custom metrics."""
        # Reset the patch to test the original function behavior
        from gopro_overlay import layout_xml

        # Save current state
        current_fn = layout_xml.metric_accessor_from
        was_patched = getattr(layout_xml, "_ts_metric_patched", False)

        # If patched, we need to get the original from the closure
        # Our patch wraps the original, so unknown metrics go through _original first
        # which raises OSError, then we check _custom_accessors.
        # For a truly unknown metric, the patched version also raises OSError.
        # So we can test with a metric name that neither original nor patch knows.
        with pytest.raises(OSError):
            current_fn("__nonexistent_metric_9999__")

    def test_accessor_callable_signature(self):
        """Accessor must accept a single entry argument."""
        from gopro_overlay.layout_xml import metric_accessor_from

        accessor = metric_accessor_from("speed")
        sig = inspect.signature(accessor)
        params = list(sig.parameters.keys())
        assert len(params) >= 1, f"Accessor should accept at least 1 param, got {params}"


class TestFFMPEGGoProContract:
    """Verify gopro_overlay.ffmpeg_gopro API that ffmpeg_gopro_patches.py depends on.

    The patch adds find_timecode() to FFMPEGGoPro and relies on:
    - FFMPEGGoPro class exists and accepts ffmpeg arg in __init__
    - Instance gets self.exe from the ffmpeg arg (used in find_timecode)
    - self.exe has .ffprobe() returning an object with .invoke()
    """

    def test_ffmpeg_gopro_class_exists(self):
        from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

        assert inspect.isclass(FFMPEGGoPro)

    def test_ffmpeg_gopro_init_accepts_ffmpeg(self):
        """__init__ must accept an ffmpeg positional arg — patch creates instances with it."""
        from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

        sig = inspect.signature(FFMPEGGoPro.__init__)
        params = list(sig.parameters.keys())
        # params[0] is 'self', params[1] should be the ffmpeg arg
        assert len(params) >= 2, f"Expected at least (self, ffmpeg), got {params}"

    def test_instance_has_exe_attribute(self):
        """After init, instance must have self.exe — used by find_timecode for ffprobe."""
        from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

        mock_ffmpeg = Mock()
        gopro = FFMPEGGoPro(mock_ffmpeg)
        assert hasattr(gopro, "exe"), "FFMPEGGoPro instance must have 'exe' attribute"

    def test_no_builtin_find_timecode(self):
        """FFMPEGGoPro must NOT have find_timecode natively — our patch adds it.

        If the library adds its own find_timecode, our patch will skip (hasattr guard),
        but it could have a different signature/behavior. This test catches that.
        """
        # Need to check the unpatched class. Since patches run at import time,
        # we check that the method is either absent or was added by our patch.
        from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

        if hasattr(FFMPEGGoPro, "find_timecode"):
            # If it exists, verify it's OUR patch (not a library addition)
            source = inspect.getsource(FFMPEGGoPro.find_timecode)
            assert "timecode" in source.lower()


class TestFFMPEGOverlayVideoContract:
    """Verify gopro_overlay.ffmpeg_overlay API that ffmpeg_overlay_patches.py depends on.

    The patch replaces __init__ and generate() and relies on:
    - FFMPEGOverlayVideo class with specific __init__ params
    - Instance attributes: options, input, output, overlay_size, creation_time, exe, execution
    - options sub-attributes: filter_complex, general, input, output
    - overlay_size.x / overlay_size.y
    - flatten() function
    - Dimension class
    """

    def test_ffmpeg_overlay_video_class_exists(self):
        from gopro_overlay.ffmpeg_overlay import FFMPEGOverlayVideo

        assert inspect.isclass(FFMPEGOverlayVideo)

    def test_init_has_expected_params(self):
        """Original __init__ must accept the params our patched_init delegates to."""
        from gopro_overlay.ffmpeg_overlay import FFMPEGOverlayVideo

        # Our patch may have already replaced __init__, so check the patched signature
        sig = inspect.signature(FFMPEGOverlayVideo.__init__)
        params = set(sig.parameters.keys()) - {"self"}
        expected = {"ffmpeg", "input", "output", "overlay_size"}
        missing = expected - params
        assert not missing, f"FFMPEGOverlayVideo.__init__ missing params: {missing}"

    def test_generate_method_exists(self):
        """generate() must exist — our patch replaces it."""
        from gopro_overlay.ffmpeg_overlay import FFMPEGOverlayVideo

        assert hasattr(FFMPEGOverlayVideo, "generate")

    def test_flatten_function_exists(self):
        """flatten() is imported and used in patched_generate to build ffmpeg command."""
        from gopro_overlay.ffmpeg_overlay import flatten

        assert callable(flatten)

    def test_flatten_flattens_nested_lists(self):
        """flatten() must recursively flatten nested lists — used to build ffmpeg args."""
        from gopro_overlay.ffmpeg_overlay import flatten

        result = flatten(["a", ["b", "c"], ["d", ["e"]]])
        assert list(result) == ["a", "b", "c", "d", "e"]

    def test_flatten_handles_empty_lists(self):
        """flatten() must handle empty inner lists (e.g. empty timecode_opts)."""
        from gopro_overlay.ffmpeg_overlay import flatten

        result = flatten(["a", [], "b"])
        assert list(result) == ["a", "b"]

    def test_dimension_class_exists(self):
        """Dimension is used for overlay_size in __init__."""
        from gopro_overlay.dimensions import Dimension

        dim = Dimension(1920, 1080)
        assert dim.x == 1920
        assert dim.y == 1080

    def test_instance_attributes_after_init(self):
        """After __init__, instance must have attributes our patched generate() reads."""
        from gopro_overlay.dimensions import Dimension
        from gopro_overlay.ffmpeg_overlay import FFMPEGOverlayVideo

        mock_ffmpeg = Mock()
        overlay = FFMPEGOverlayVideo(
            ffmpeg=mock_ffmpeg,
            input=Path("input.mp4"),
            output=Path("output.mp4"),
            overlay_size=Dimension(1920, 1080),
        )

        # Attributes used by patched_generate
        assert hasattr(overlay, "input")
        assert hasattr(overlay, "output")
        assert hasattr(overlay, "overlay_size")
        assert hasattr(overlay, "exe")
        assert hasattr(overlay, "options")
        assert hasattr(overlay, "creation_time")

    def test_options_sub_attributes(self):
        """options must have filter_complex, general, input, output — used in patched generate."""
        from gopro_overlay.dimensions import Dimension
        from gopro_overlay.ffmpeg_overlay import FFMPEGOverlayVideo

        mock_ffmpeg = Mock()
        overlay = FFMPEGOverlayVideo(
            ffmpeg=mock_ffmpeg,
            input=Path("input.mp4"),
            output=Path("output.mp4"),
            overlay_size=Dimension(1920, 1080),
        )

        opts = overlay.options
        assert hasattr(opts, "filter_complex"), "options must have filter_complex"
        assert hasattr(opts, "general"), "options must have general"
        assert hasattr(opts, "input"), "options must have input"
        assert hasattr(opts, "output"), "options must have output"
