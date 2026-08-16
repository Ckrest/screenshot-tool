from unittest.mock import MagicMock, patch

from screenshot_tool.models import CaptureRequest
from screenshot_tool.service import ScreenshotController


@patch("screenshot_tool.service.ScreenshotNotifications")
def test_second_interactive_request_during_freeze_reuses_session(
    _notifications,
) -> None:
    controller = ScreenshotController(MagicMock(), MagicMock())
    controller.state = "freezing"
    controller.request = CaptureRequest(mode="interactive", request_id="first")
    controller.participants = ["first"]
    controller.request_capture(CaptureRequest(mode="interactive", request_id="second"))
    assert controller._force_fullscreen is True
    assert controller.participants == ["first", "second"]
    controller.executor.shutdown(wait=False, cancel_futures=True)


@patch("screenshot_tool.service.ScreenshotNotifications")
def test_second_interactive_request_closes_visible_overlay_as_fullscreen(
    _notifications,
) -> None:
    controller = ScreenshotController(MagicMock(), MagicMock())
    controller.state = "selecting"
    controller.request = CaptureRequest(mode="interactive", request_id="first")
    controller.participants = ["first"]
    controller.overlay = MagicMock()
    controller.request_capture(CaptureRequest(mode="interactive", request_id="second"))
    controller.overlay.confirm_fullscreen.assert_called_once_with()
    controller.executor.shutdown(wait=False, cancel_futures=True)
