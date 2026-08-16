from unittest.mock import MagicMock

from screenshot_tool.ui.overlay import ScreenshotOverlay, point_near_rectangle


def test_instruction_proximity_includes_padding_but_not_distant_motion() -> None:
    assert point_near_rectangle(430, 100, 500, 20, 360, 44)
    assert point_near_rectangle(900, 120, 500, 20, 360, 44)
    assert not point_near_rectangle(300, 300, 500, 20, 360, 44)


def test_dismissing_instructions_updates_every_output_once() -> None:
    overlay = ScreenshotOverlay.__new__(ScreenshotOverlay)
    overlay._instructions_visible = True
    overlay.views = [MagicMock(), MagicMock()]

    overlay._dismiss_instructions()
    overlay._dismiss_instructions()

    assert overlay._instructions_visible is False
    for view in overlay.views:
        view.hide_instructions.assert_called_once_with()


def test_motion_only_dismisses_instructions_near_the_label() -> None:
    overlay = ScreenshotOverlay.__new__(ScreenshotOverlay)
    overlay._instructions_visible = True
    overlay._dismiss_instructions = MagicMock()
    view = MagicMock()
    view.pointer_near_instructions.side_effect = [False, True]

    overlay._dismiss_instructions_near(view, 100, 100)
    overlay._dismiss_instructions_near(view, 600, 50)

    overlay._dismiss_instructions.assert_called_once_with()
