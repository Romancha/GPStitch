"""Tests for smooth_map_patches: maps moved by fractions of a pixel (issue #26)."""

import random
from types import SimpleNamespace

import geotiler
import pytest
from gopro_overlay.point import Coordinate, Point
from gopro_overlay.units import units
from gopro_overlay.widgets.map import MovingJourneyMap, MovingMap
from PIL import Image, ImageChops, ImageDraw

from gpstitch.patches.smooth_map_patches import patch_smooth_maps, view_transform

ZOOM = 16
SIZE = 256
WORLD_SIZE = 1024
# Texture pixel of the test location; the world texture is centred on it
HOME = (WORLD_SIZE / 2, WORLD_SIZE / 2)
# Marker drawn by the widgets at the view centre: stock blurs it with the rotation
MARKER_BOX = (SIZE // 2 - 8, SIZE // 2 - 8, SIZE // 2 + 9, SIZE // 2 + 9)


def _noise(width: int, height: int, seed: int = 1) -> Image.Image:
    data = random.Random(seed).randbytes(width * height * 3)
    return Image.frombytes("RGB", (width, height), data).convert("RGBA")


# A map image covering WORLD_SIZE x WORLD_SIZE pixels around the test location, so
# renders of any layout inside it share the same pixels
WORLD = geotiler.Map(center=(4.88, 52.36), zoom=ZOOM, size=(WORLD_SIZE, WORLD_SIZE))
TEXTURE = _noise(WORLD_SIZE, WORLD_SIZE)


def _world_px(map) -> tuple[int, int]:
    """World pixel (at ZOOM) of a map image's top-left corner."""
    w, h = map.size
    return (
        map.origin[0] * map.provider.tile_width - map.offset[0] - w // 2,
        map.origin[1] * map.provider.tile_height - map.offset[1] - h // 2,
    )


def _renderer(calls: list | None = None):
    """Offline MovingMap renderer: crops the map's area out of TEXTURE."""
    world_left, world_top = _world_px(WORLD)

    def render(map):
        if calls is not None:
            calls.append(map)
        left, top = _world_px(map)
        x, y = left - world_left, top - world_top
        return TEXTURE.crop((x, y, x + map.size[0], y + map.size[1]))

    return render


def _location(x: float, y: float) -> Point:
    """Location at TEXTURE pixel coordinate (x, y)."""
    lon, lat = WORLD.geocode((x, y))
    return Point(lat=lat, lon=lon)


def _deg(value: float):
    return units.Quantity(value, units.degree)


def _moving_map(state: dict, renderer=None, **kwargs) -> MovingMap:
    """Opaque MovingMap following state["location"] and state["azimuth"]."""
    return MovingMap(
        at=Coordinate(0, 0),
        location=lambda: state["location"],
        azimuth=lambda: state.get("azimuth"),
        renderer=renderer or _renderer(),
        size=SIZE,
        zoom=ZOOM,
        **{"opacity": 1.0, **kwargs},
    )


def _draw(widget, draw_function=None) -> Image.Image:
    """Widget drawn onto an empty image of its size, by draw_function or its current draw."""
    image = Image.new("RGBA", (widget.size, widget.size))
    (draw_function or type(widget).draw)(widget, image, ImageDraw.Draw(image))
    return image


def _max_diff(a: Image.Image, b: Image.Image, exclude=None) -> int:
    a, b = a.copy(), b.copy()
    if exclude:
        a.paste((0, 0, 0, 0), exclude)
        b.paste((0, 0, 0, 0), exclude)
    return max(high for _, high in ImageChops.difference(a, b).getextrema())


def _band(image: Image.Image, dx: int = 0) -> Image.Image:
    """A band of the view above the marker and inside the border, starting dx pixels right."""
    return image.crop((16 + dx, 16, SIZE - 17 + dx, 100))


@pytest.fixture(autouse=True)
def stock_draw(monkeypatch):
    """Stock draw methods; patch_smooth_maps patches the classes globally, so undo it after each test."""
    monkeypatch.setattr(MovingMap, "draw", MovingMap.draw)
    monkeypatch.setattr(MovingJourneyMap, "draw", MovingJourneyMap.draw)
    monkeypatch.setattr(MovingMap, "_ts_smooth_map_patched", False, raising=False)
    return SimpleNamespace(moving_map=MovingMap.draw, moving_journey_map=MovingJourneyMap.draw)


@pytest.fixture
def smooth_maps():
    patch_smooth_maps()


class TestViewTransform:
    @pytest.mark.parametrize("angle", [0, 30, 90, 135, 200, 359])
    def test_matches_stock_rotate_and_crop(self, angle):
        """MovingMap._redraw rotates the hypotenuse image about its centre, then crops."""
        hypotenuse = 362
        image = _noise(hypotenuse, hypotenuse)
        half = hypotenuse / 2
        bounds = (half - SIZE / 2, half - SIZE / 2, half + SIZE / 2, half + SIZE / 2)

        stock = image.rotate(angle, resample=Image.BILINEAR).crop(bounds)
        view = image.transform(
            (SIZE, SIZE),
            Image.Transform.AFFINE,
            view_transform((half, half), SIZE, angle),
            resample=Image.Resampling.BILINEAR,
        )

        assert _max_diff(stock, view) <= 1

    def test_unrotated_view_is_a_crop_at_any_offset(self):
        assert view_transform((100.25, 50.5), 20) == pytest.approx((1, 0, 90.25, 0, 1, 40.5))


@pytest.mark.usefixtures("smooth_maps")
class TestMovingMap:
    @pytest.mark.parametrize(
        ("azimuth", "rotate"),
        [(None, True), (0, True), (30, True), (90, True), (-45, True), (30, False)],
    )
    def test_matches_stock_at_whole_pixel(self, stock_draw, azimuth, rotate):
        state = {"location": _location(*HOME), "azimuth": None if azimuth is None else _deg(azimuth)}

        stock = _draw(_moving_map(state, rotate=rotate), stock_draw.moving_map)
        smooth = _draw(_moving_map(state, rotate=rotate))

        assert _max_diff(stock, smooth, exclude=MARKER_BOX) <= 1

    def test_matches_stock_with_rounded_translucent_border(self, stock_draw):
        state = {"location": _location(*HOME), "azimuth": _deg(30)}
        kwargs = {"corner_radius": 35, "opacity": 0.7}

        stock = _draw(_moving_map(state, **kwargs), stock_draw.moving_map)
        smooth = _draw(_moving_map(state, **kwargs))

        assert _max_diff(stock, smooth, exclude=MARKER_BOX) <= 1

    def test_moves_by_fractions_of_a_pixel(self):
        """Stock keeps the same image until the location has moved a whole pixel."""
        state = {"location": _location(*HOME)}
        widget = _moving_map(state)
        frames = []
        for step in range(5):
            state["location"] = _location(HOME[0] + step / 4, HOME[1])
            frames.append(_draw(widget))

        for before, after in zip(frames, frames[1:], strict=False):
            assert _max_diff(before, after, exclude=MARKER_BOX) > 10
        # Halfway between two whole pixels is their bilinear average
        start, half, whole = frames[0], frames[2], frames[4]
        average = Image.blend(start, whole, 0.5)
        assert _max_diff(half, average, exclude=MARKER_BOX) <= 1
        # A whole pixel east shifts the map one pixel west
        assert _max_diff(_band(whole), _band(start, dx=1)) <= 1

    def test_turns_with_the_heading_alone(self):
        state = {"location": _location(*HOME), "azimuth": _deg(10)}
        widget = _moving_map(state)
        before = _draw(widget)
        state["azimuth"] = _deg(10.5)

        assert _max_diff(before, _draw(widget), exclude=MARKER_BOX) > 10

    def test_rotated_view_has_no_gaps(self):
        """The base map is large enough for any heading, at any sub-pixel offset."""
        for offset in (-0.49, 0.49):
            for azimuth in (45, 135, 225, 315):
                state = {"location": _location(HOME[0] + offset, HOME[1] + offset), "azimuth": _deg(azimuth)}
                widget = _moving_map(state)
                # The stock border sets the alpha of the whole view, which would hide gaps
                widget.border = SimpleNamespace(rounded=lambda image: image)

                alpha_low, _ = _draw(widget).getchannel("A").getextrema()
                assert alpha_low == 255, f"gap at offset {offset}, heading {azimuth}"

    def test_renders_tiles_only_when_the_layout_changes(self):
        calls = []
        state = {"location": _location(*HOME)}
        widget = _moving_map(state, renderer=_renderer(calls))

        _draw(widget)
        cached = widget.cached
        _draw(widget)
        assert len(calls) == 1
        assert widget.cached is cached

        state["location"] = _location(HOME[0] + 0.3, HOME[1])
        _draw(widget)
        assert len(calls) == 1

        state["location"] = _location(HOME[0] + 2, HOME[1])
        _draw(widget)
        assert len(calls) == 2

    def test_draws_nothing_without_location(self):
        calls = []
        widget = _moving_map({"location": Point(lat=None, lon=None)}, renderer=_renderer(calls))

        assert _draw(widget).getbbox() is None
        assert calls == []

    def test_marker_is_not_blurred(self):
        state = {"location": _location(*HOME), "azimuth": _deg(30)}

        frame = _draw(_moving_map(state))

        # Stock rotates the marker with the map, blending its outline into the tiles
        assert frame.getpixel((SIZE // 2 - 6, SIZE // 2)) == (0, 0, 0, 255)
        assert frame.getpixel((SIZE // 2, SIZE // 2)) == (0, 0, 255, 255)


@pytest.mark.usefixtures("smooth_maps")
class TestMovingJourneyMap:
    @staticmethod
    def _widget(position: tuple[float, float], size: int = 64) -> MovingJourneyMap:
        widget = MovingJourneyMap(
            timeseries=None,
            privacy_zone=None,
            location=lambda: Point(lat=0.0, lon=0.0),
            size=size,
            zoom=ZOOM,
            renderer=None,
        )
        widget.cached_map = SimpleNamespace(rev_geocode=lambda location: position)
        widget.cached_map_image = TEXTURE
        return widget

    @pytest.mark.parametrize("position", [(500, 300), (10, 10), (1020, 1000)])
    def test_matches_stock_at_whole_pixel(self, stock_draw, position):
        """Including the window clamped at the edges of the map."""
        stock = _draw(self._widget(position), stock_draw.moving_journey_map)

        assert _max_diff(stock, _draw(self._widget(position))) == 0

    def test_scrolls_by_fractions_of_a_pixel(self):
        start = _draw(self._widget((500, 300)))
        half = _draw(self._widget((500.5, 300)))
        whole = _draw(self._widget((501, 300)))

        marker = (24, 24, 41, 41)
        assert _max_diff(half, Image.blend(start, whole, 0.5), exclude=marker) <= 1
        assert _max_diff(half, start, exclude=marker) > 10


class TestPatchSmoothMaps:
    def test_replaces_both_draws(self, stock_draw):
        patch_smooth_maps()
        assert MovingMap.draw is not stock_draw.moving_map
        assert MovingJourneyMap.draw is not stock_draw.moving_journey_map

    def test_patch_is_idempotent(self):
        patch_smooth_maps()
        patched = MovingMap.draw, MovingJourneyMap.draw
        patch_smooth_maps()
        assert (MovingMap.draw, MovingJourneyMap.draw) == patched
