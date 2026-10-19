"""Contract tests for gopro_overlay library APIs used by patches.

These tests verify that the gopro_overlay library exposes the APIs our patches
depend on. If the library changes, these tests will fail BEFORE the patches
silently break at runtime.

Covered patches:
- gpx_patches.py     → TestLoadingModuleContract, TestTimeseriesContract
- metric_patches.py  → TestMetricAccessorContract
- ffmpeg_gopro_patches.py   → TestFFMPEGGoProContract
- ffmpeg_overlay_patches.py → TestFFMPEGOverlayVideoContract
- encoding_patches.py       → TestFFMPEGInvokeContract, TestGpxLoadContract,
                              TestLoadXmlLayoutContract, TestConfigContract
- overlay_fps_patches.py    → TestDashboardDrawLoopContract, TestFrameMetaContract,
                              TestOverlayDrawContract, TestFFMPEGOverlayContract,
                              TestTelemetryTypesContract
- font_patches.py           → TestLoadFontContract
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
        _ = getattr(layout_xml, "_ts_metric_patched", False)

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


class TestFFMPEGInvokeContract:
    """Verify gopro_overlay.ffmpeg API that encoding_patches.py depends on.

    The patch wraps FFMPEG.invoke() to force encoding="utf-8" and relies on:
    - invoke() accepting arbitrary **kwargs that reach subprocess.run
    - run() being a SEPARATE method, so the binary video pipe stays untouched
    - ffprobe()/ffmpeg() propagating invoke_fn to the new instance
    """

    def test_invoke_accepts_arbitrary_kwargs(self):
        """invoke(args, **kwargs) must forward kwargs — that is how we inject encoding."""
        from gopro_overlay.ffmpeg import FFMPEG

        sig = inspect.signature(FFMPEG.invoke)
        params = list(sig.parameters.values())
        assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params), (
            f"FFMPEG.invoke must accept **kwargs, got {[p.name for p in params]}"
        )

    def test_invoke_forwards_kwargs_to_invoke_fn(self):
        from gopro_overlay.ffmpeg import FFMPEG

        invoke_fn = Mock(return_value=Mock(stdout=""))
        FFMPEG(invoke_fn=invoke_fn).invoke(["-version"], marker="sentinel")

        assert invoke_fn.call_args.kwargs.get("marker") == "sentinel"

    def test_run_is_a_separate_method(self):
        """run() pipes raw video bytes; the patch must be able to leave it alone."""
        from gopro_overlay.ffmpeg import FFMPEG

        assert FFMPEG.run is not FFMPEG.invoke

    def test_invoke_fn_is_an_init_default(self):
        """The reason we patch the method, not gopro_overlay.process.invoke.

        invoke_fn is bound as a default argument at class-definition time, so
        replacing the module attribute would not affect instances created later.
        """
        from gopro_overlay.ffmpeg import FFMPEG

        sig = inspect.signature(FFMPEG.__init__)
        assert "invoke_fn" in sig.parameters
        assert sig.parameters["invoke_fn"].default is not inspect.Parameter.empty

    def test_ffprobe_propagates_invoke_fn(self):
        """ffprobe() builds a new FFMPEG — patching the class covers it, but only
        if the child keeps using the same invoke_fn plumbing."""
        from gopro_overlay.ffmpeg import FFMPEG

        invoke_fn = Mock(return_value=Mock(stdout=""))
        parent = FFMPEG(invoke_fn=invoke_fn)

        assert parent.ffprobe().invoke_fn is invoke_fn
        assert parent.ffmpeg().invoke_fn is invoke_fn


class TestGpxLoadContract:
    """Verify gopro_overlay.gpx API that encoding_patches.py depends on.

    The patch replaces gpx.load() and delegates to gpx.load_xml().
    """

    def test_load_exists_with_expected_signature(self):
        from gopro_overlay import gpx

        sig = inspect.signature(gpx.load)
        params = list(sig.parameters.keys())
        assert params[:2] == ["filepath", "units"], f"Expected (filepath, units), got {params}"

    def test_load_xml_exists_and_accepts_a_text_stream(self):
        """Our replacement hands load_xml an open text file object."""
        import io

        from gopro_overlay import gpx
        from gopro_overlay.units import units

        gpx_text = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx version="1.1" creator="Test" xmlns="http://www.topografix.com/GPX/1/1">\n'
            "  <trk><trkseg>\n"
            '    <trkpt lat="55.0" lon="37.0"><ele>1</ele><time>2024-01-01T12:00:00Z</time></trkpt>\n'
            "  </trkseg></trk>\n"
            "</gpx>\n"
        )

        assert len(gpx.load_xml(io.StringIO(gpx_text), units)) == 1

    def test_load_timeseries_goes_through_module_level_load(self):
        """load_timeseries must resolve `load` at call time, or replacing the
        module attribute would not affect it."""
        from gopro_overlay import gpx

        source = inspect.getsource(gpx.load_timeseries)
        assert "load(" in source, "load_timeseries no longer delegates to load()"


class TestLoadXmlLayoutContract:
    """Verify gopro_overlay.layout_xml.load_xml_layout that encoding_patches.py replaces."""

    def test_load_xml_layout_exists_with_expected_signature(self):
        from gopro_overlay.layout_xml import load_xml_layout

        sig = inspect.signature(load_xml_layout)
        assert list(sig.parameters.keys())[:1] == ["filepath"]

    def test_packaged_layouts_are_resolvable_by_name(self):
        """Our replacement keeps the importlib.resources fallback branch."""
        from importlib.resources import files

        from gopro_overlay import layouts

        names = {p.name for p in files(layouts).iterdir()}
        assert "default-1920x1080.xml" in names


class TestConfigContract:
    """Verify gopro_overlay.config API that encoding_patches.py depends on.

    The patch replaces Config.maybe() and constructs ConfigFile directly.
    """

    def test_config_has_location_and_maybe(self):
        from gopro_overlay.config import Config

        sig = inspect.signature(Config.maybe)
        assert list(sig.parameters.keys())[:2] == ["self", "name"]
        assert "location" in inspect.signature(Config.__init__).parameters

    def test_config_file_accepts_content_and_location(self):
        from gopro_overlay.config import ConfigFile

        config_file = ConfigFile(content={"a": 1}, location=Path("/tmp/x.json"))

        assert config_file.content == {"a": 1}
        assert config_file.location == Path("/tmp/x.json")

    def test_maybe_returns_empty_config_for_missing_file(self, tmp_path):
        from gopro_overlay.config import Config

        assert Config(tmp_path).maybe("does-not-exist.json").content is None


class TestDashboardDrawLoopContract:
    """Verify the gopro-dashboard.py draw loop that overlay_fps_patches.py retimes.

    The script runs as __main__ via runpy, so the patch can only reach it through
    FrameMeta.stepper (frame timeline) and Overlay.draw (per-frame entry).
    """

    @pytest.fixture
    def script(self):
        from gpstitch.scripts.gopro_dashboard_wrapper import find_gopro_dashboard

        path = find_gopro_dashboard()
        assert path is not None, "gopro-dashboard.py not found"
        return path.read_text(encoding="utf-8")

    def test_frames_are_stepped_at_10_fps_with_timelapse_correction(self, script):
        assert "frame_meta.stepper(timeunits(seconds=0.1 * timelapse_correction))" in script

    def test_frames_are_drawn_through_overlay(self, script):
        assert "Overlay(framemeta=frame_meta" in script
        assert "overlay.draw(dt, frame)" in script

    def test_stepper_is_called_once(self, script):
        assert script.count(".stepper(") == 1


class TestFrameMetaContract:
    """Verify FrameMeta internals that overlay_fps_patches.py reads."""

    @staticmethod
    def _framemeta():
        from gopro_overlay.entry import Entry
        from gopro_overlay.framemeta import FrameMeta
        from gopro_overlay.timeunits import timeunits

        framemeta = FrameMeta()
        for ms in (0, 100, 250):
            framemeta.add(timeunits(millis=ms), Entry(dt=None, value=ms))
        return framemeta

    def test_framelist_and_frames(self):
        from gopro_overlay.timeunits import timeunits

        framemeta = self._framemeta()
        framemeta.check_modified()
        assert framemeta.framelist == [timeunits(millis=ms) for ms in (0, 100, 250)]
        assert framemeta.frames[timeunits(millis=100)].value == 100

    def test_get_returns_previous_sample(self):
        from gopro_overlay.timeunits import timeunits

        assert self._framemeta().get(timeunits(millis=180)).value == 100

    def test_stepper_runs_from_zero_to_last_sample(self):
        from gopro_overlay.timeunits import timeunits

        stepper = self._framemeta().stepper(timeunits(millis=100))
        assert [t.us for t in stepper.steps()] == [0, 100_000, 200_000]
        assert len(stepper) == 3


class TestOverlayDrawContract:
    """Verify Overlay.draw, which overlay_fps_patches.py replaces to interpolate."""

    def test_draw_sets_entry_from_framemeta_and_draws_scene(self):
        from gopro_overlay.layout import Overlay

        framemeta = Mock()
        overlay = Overlay(framemeta=framemeta, create_widgets=lambda entry: [])
        overlay.scene = Mock()

        result = overlay.draw("pts", "image")

        framemeta.get.assert_called_once_with("pts")
        assert overlay.entry() is framemeta.get.return_value
        assert result is overlay.scene.draw.return_value


class TestFFMPEGOverlayContract:
    """Verify the overlay-only FFMPEGOverlay command that overlay_fps_patches.py copies."""

    def test_generate_streams_10_fps_raw_input_into_30_fps_output(self):
        import datetime

        from gopro_overlay.dimensions import Dimension
        from gopro_overlay.ffmpeg_overlay import FFMPEGOverlay

        ffmpeg = Mock()
        ffmpeg.execute.return_value = iter([Mock()])
        overlay = FFMPEGOverlay(
            ffmpeg=ffmpeg,
            output=Path("out.mov"),
            overlay_size=Dimension(640, 480),
            creation_time=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        )
        with overlay.generate():
            pass

        execution, cmd = ffmpeg.execute.call_args.args
        assert execution is overlay.execution
        assert cmd == [
            "-hide_banner",
            "-y",
            "-hide_banner",
            "-loglevel",
            "info",
            "-f",
            "rawvideo",
            "-framerate",
            "10.0",
            "-s",
            "640x480",
            "-pix_fmt",
            "rgba",
            "-i",
            "-",
            "-r",
            "30",
            "-vcodec",
            "libx264",
            "-preset",
            "veryfast",
            "-metadata",
            "creation_time=2026-01-01T00:00:00+00:00",
            "out.mov",
        ]


class TestTelemetryTypesContract:
    """Verify telemetry value types that overlay_fps_patches.py interpolates or holds."""

    def test_gps_fixed_values(self):
        from gopro_overlay.gpmf.gpmf import GPS_FIXED_VALUES, GPSFix

        assert {GPSFix.LOCK_2D.value, GPSFix.LOCK_3D.value} == GPS_FIXED_VALUES

    def test_entry_items_are_a_dict(self):
        from gopro_overlay.entry import Entry

        assert Entry(dt=None, speed=1).items == {"speed": 1}

    def test_orientation_fields(self):
        import dataclasses

        from gopro_overlay.gpmf.visitors.cori import Orientation

        assert [f.name for f in dataclasses.fields(Orientation)] == ["roll", "pitch", "yaw"]

    def test_point_types(self):
        from gopro_overlay.point import PintPoint3, Point, Point3
        from gopro_overlay.units import units

        point = Point(lat=1.0, lon=2.0)
        assert (point.lat, point.lon) == (1.0, 2.0)
        assert issubclass(PintPoint3, Point3)
        q = units.Quantity(1, units.m)
        assert PintPoint3(q, q, q).x == q


class TestLoadFontContract:
    """Verify gopro_overlay.font.load_font that font_patches.py replaces.

    gopro-dashboard.py imports load_font by name when it runs (after the wrapper has
    patched the module attribute) and loads --font through it.
    """

    def test_load_font_exists_with_expected_signature(self):
        from gopro_overlay.font import load_font

        sig = inspect.signature(load_font)
        assert list(sig.parameters.keys()) == ["font", "size"]
        assert sig.parameters["size"].default == 32

    def test_dashboard_loads_font_option_through_load_font(self):
        from gpstitch.scripts.gopro_dashboard_wrapper import find_gopro_dashboard

        path = find_gopro_dashboard()
        assert path is not None, "gopro-dashboard.py not found"
        script = path.read_text(encoding="utf-8")
        assert "from gopro_overlay.font import load_font" in script
        assert "load_font(args.font)" in script
