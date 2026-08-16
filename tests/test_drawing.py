from unittest.mock import MagicMock, patch

from screenshot_tool.models import CoordinateMapper, SelectionModel
from screenshot_tool.ui.drawing import (
    MAGNIFIER_DIAMETER,
    MAGNIFIER_MARGIN,
    MAGNIFIER_ZOOM,
    OverlayDrawing,
    magnifier_geometry,
)


def test_magnifier_is_larger_and_shows_more_source_pixels() -> None:
    _x, _y, size = magnifier_geometry(500, 400, 1920, 1080)
    assert size == MAGNIFIER_DIAMETER == 480
    assert size / MAGNIFIER_ZOOM == 60


def test_magnifier_flips_away_from_bottom_right_edge() -> None:
    x, y, size = magnifier_geometry(1900, 1060, 1920, 1080)
    assert x < 1900 - size
    assert y < 1060 - size
    assert x >= MAGNIFIER_MARGIN
    assert y >= MAGNIFIER_MARGIN
    assert x + size <= 1920 - MAGNIFIER_MARGIN
    assert y + size <= 1080 - MAGNIFIER_MARGIN


def test_magnifier_uses_a_circular_clip_and_border() -> None:
    model = SelectionModel(100, 100, (50, 50))
    drawing = OverlayDrawing(model, CoordinateMapper(100, 100), object(), [])
    context = MagicMock()
    context.get_source.return_value = MagicMock()

    with patch("screenshot_tool.ui.drawing.Gdk.cairo_set_source_pixbuf"):
        drawing._magnifier(context, 300, 200, 1000, 800)

    # One arc clips the image, followed by dark and light circular borders.
    assert context.arc.call_count == 3
    context.clip.assert_called_once_with()
    context.rectangle.assert_not_called()
