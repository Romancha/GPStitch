"""Patch gopro_overlay map widgets to move by fractions of a pixel (smooth animation).

With smooth animation the location is interpolated for every overlay frame, so at
50/60 FPS it moves a fraction of a map pixel per frame. The stock map widgets only
move in whole pixels:

- MovingMap redraws only after the location has moved a whole map pixel
  (PerceptibleMovementCheck), geotiler rounds the map centre to a whole pixel, and the
  heading rotation is only updated on those redraws. At zoom 16 and 50 km/h the map
  changed ~11 times per second in a 59.94 FPS render (issue #26).
- MovingJourneyMap crops its view window at a whole pixel.

The patched widgets keep the stock tile rendering and apply the sub-pixel remainder
(and the heading) with a bilinear affine transform on every frame.

Applied only in the render subprocess, together with overlay_fps_patches (via the
wrapper's --ts-overlay-fps), so previews and renders without the option keep the
stock behaviour.
"""

import logging
import math

import geotiler
from gopro_overlay.widgets.map import MovingJourneyMap, MovingMap, draw_marker
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Extra base map pixels on each side of MovingMap's hypotenuse: the rotated view
# reaches size/√2 from the location, which is up to 0.5 px off the rounded map centre,
# bilinear sampling reads another 0.5 px, and the hypotenuse is truncated to an int.
BASE_MAP_PADDING = 2


def view_transform(center: tuple[float, float], size: int, angle: float = 0.0) -> tuple[float, ...]:
    """Image.transform AFFINE data for a size x size view centred on an image point.

    The view is rotated counter-clockwise by angle degrees about center, like
    Image.rotate. AFFINE data maps each output point to the input point it samples.
    """
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)
    half = size / 2
    return (
        cos,
        -sin,
        center[0] - half * (cos - sin),
        sin,
        cos,
        center[1] - half * (sin + cos),
    )


def _heading(widget) -> float:
    """MovingMap rotation in degrees, under the same condition as MovingMap._redraw."""
    azimuth = widget.azimuth()
    if not (azimuth and widget.rotate):
        return 0.0
    return azimuth.to("degree").magnitude


def _moving_map_draw(self, image: Image.Image, draw: ImageDraw.ImageDraw):
    """MovingMap.draw with the map placed and rotated by fractions of a pixel.

    Mirrors gopro_overlay 0.129.0 MovingMap.draw/_redraw except that:
    - tiles are rendered only when geotiler's whole-pixel layout changes, and the
      location's sub-pixel remainder is applied together with the rotation
    - the view is redrawn whenever the location or heading changes, not after each
      whole pixel of movement
    - the marker is drawn after the rotation, so it is not blurred by it
    """
    location = self.location()
    if location.lon is None or location.lat is None:
        return

    side = self.hypotenuse + 2 * BASE_MAP_PADDING
    map = geotiler.Map(center=(location.lon, location.lat), zoom=self.zoom, size=(side, side))

    layout = (map.origin, map.offset)
    if layout != getattr(self, "_ts_layout", None):
        self._ts_base = self.renderer(map)
        self._ts_layout = layout

    # Within ±0.5 px of the base centre: geotiler rounded the centre to a whole pixel
    center = map.rev_geocode((location.lon, location.lat))
    heading = _heading(self)
    view = (layout, center, heading)
    if view != getattr(self, "_ts_view", None):
        frame = self._ts_base.transform(
            (self.size, self.size),
            Image.Transform.AFFINE,
            view_transform(center, self.size, heading),
            resample=Image.Resampling.BILINEAR,
        )
        draw_marker(ImageDraw.Draw(frame), (self.size / 2, self.size / 2), 6)
        self.cached = self.border.rounded(frame)
        self._ts_view = view

    image.alpha_composite(self.cached, self.at.tuple())


def _moving_journey_map_draw(self, image: Image.Image, draw: ImageDraw.ImageDraw):
    """MovingJourneyMap.draw with the view window placed by fractions of a pixel.

    Mirrors gopro_overlay 0.129.0 MovingJourneyMap.draw except that the window is
    sampled at the exact location instead of cropped at a whole pixel.
    """
    if self.cached_map is None:
        self.cached_map, self.cached_map_image = self._redraw()

    location = self.location()
    if location.lon is not None and location.lat is not None:
        x, y = self.cached_map.rev_geocode((location.lon, location.lat))
        width, height = self.cached_map_image.size
        half = int(self.size / 2)

        # view_window() without rounding: at whole pixels this samples exactly its crop
        left = max(0.0, min(width - self.size, x - half))
        top = max(0.0, min(height - self.size, y - half))
        window = self.cached_map_image.transform(
            (self.size, self.size),
            Image.Transform.AFFINE,
            (1, 0, left, 0, 1, top),
            resample=Image.Resampling.BILINEAR,
        )

        image.alpha_composite(window, (0, 0))
        draw_marker(draw, (half, half), 6)


def patch_smooth_maps() -> None:
    """Make MovingMap and MovingJourneyMap move by fractions of a pixel every frame."""
    if getattr(MovingMap, "_ts_smooth_map_patched", False):
        logger.debug("Smooth maps already patched, skipping")
        return

    MovingMap.draw = _moving_map_draw
    MovingJourneyMap.draw = _moving_journey_map_draw
    MovingMap._ts_smooth_map_patched = True
    logger.info("Patched map widgets for sub-pixel movement")
