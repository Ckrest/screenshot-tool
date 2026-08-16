from unittest.mock import MagicMock, patch

from screenshot_tool.wayfire import get_window_geometries


def _view(view_id: int) -> dict:
    return {
        "id": view_id,
        "mapped": True,
        "minimized": False,
        "type": "toplevel",
        "layer": "workspace",
        "app-id": "kitty",
        "title": "Same title",
        "geometry": {"x": 20, "y": 30, "width": 800, "height": 600},
        "last-focus-timestamp": view_id,
    }


@patch("screenshot_tool.wayfire._get_socket")
def test_geometry_carries_compositor_capture_identifier(mock_get_socket) -> None:
    socket = MagicMock()
    socket.list_views.return_value = [_view(41), _view(42)]
    socket.send_json.return_value = {
        "status": "ok",
        "identifiers": [
            {"view-id": 41, "identifier": "opaque-a"},
            {"view-id": 42, "identifier": "opaque-b"},
        ],
    }
    mock_get_socket.return_value = socket

    windows = get_window_geometries()

    assert {item["capture_identifier"] for item in windows} == {
        "opaque-a",
        "opaque-b",
    }
    socket.close.assert_called_once()


@patch("screenshot_tool.wayfire._get_socket")
def test_missing_identifier_endpoint_fails_closed(mock_get_socket) -> None:
    socket = MagicMock()
    socket.list_views.return_value = [_view(41)]
    socket.send_json.side_effect = RuntimeError("method not found")
    mock_get_socket.return_value = socket

    assert get_window_geometries()[0]["capture_identifier"] == ""
