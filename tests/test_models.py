import pytest
from screenshot_tool.models import (
    CoordinateMapper,
    OutputLayout,
    RawFrame,
    Rect,
    SelectionModel,
)


def test_raw_crop_copies_rows_with_source_stride() -> None:
    rows = bytes(range(24)) + bytes(range(24, 48))
    frame = RawFrame(width=4, height=2, stride=24, pixels=rows)
    cropped = frame.crop(Rect(1, 0, 2, 2))
    assert (cropped.width, cropped.height, cropped.stride) == (2, 2, 8)
    assert cropped.pixels == rows[4:12] + rows[28:36]


def test_empty_crop_is_rejected() -> None:
    frame = RawFrame(2, 2, 8, b"\0" * 16)
    with pytest.raises(ValueError, match="empty"):
        frame.crop(Rect(5, 5, 1, 1))


def test_coordinate_mapper_round_trip() -> None:
    mapper = CoordinateMapper(200, 100)
    assert mapper.widget_to_frame(50, 25, 100, 50) == (100, 50)
    assert mapper.frame_to_widget(100, 50, 100, 50) == (50, 25)


def test_selection_normalizes_drag_direction_and_nudges() -> None:
    model = SelectionModel(100, 80, (50, 40))
    model.begin()
    model.move(10, 5)
    assert model.selection == Rect(10, 5, 40, 35)
    model.nudge(-1, 1)
    assert (model.cursor_x, model.cursor_y) == (9, 6)


def test_logical_geometry_maps_through_composite_scale_and_origin() -> None:
    output = OutputLayout(
        name="DP-2",
        logical_x=-1280,
        logical_y=0,
        logical_width=1280,
        logical_height=720,
        buffer_width=2560,
        buffer_height=1440,
        scale=2.0,
        transform="normal",
        frame_x=0,
        frame_y=0,
        frame_width=2560,
        frame_height=1440,
    )
    frame = RawFrame(
        6400,
        2160,
        25600,
        b"",
        logical_origin=(-1280, 0),
        canvas_scale=2.0,
        outputs=(output,),
    )

    assert frame.logical_point_to_frame(-1280, 0) == (0, 0)
    assert frame.logical_rect_to_frame(Rect(-640, 180, 640, 360)) == Rect(
        1280, 360, 1280, 720
    )


def test_viewport_mapper_offsets_each_monitor_in_shared_frame() -> None:
    mapper = CoordinateMapper(3000, 1000, viewport=Rect(1000, 0, 2000, 1000))
    assert mapper.widget_to_frame(0, 0, 1000, 500) == (1000, 0)
    assert mapper.widget_to_frame(1000, 500, 1000, 500) == (2999, 999)
    assert mapper.frame_to_widget(2000, 500, 1000, 500) == (500, 250)
