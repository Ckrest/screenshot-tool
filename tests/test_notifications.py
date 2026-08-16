from pathlib import Path
from unittest.mock import MagicMock

from gi.repository import GLib
from screenshot_tool.notifications import ScreenshotNotifications


def test_previous_popup_is_closed_before_distinct_notification() -> None:
    client = ScreenshotNotifications.__new__(ScreenshotNotifications)
    client.proxy = MagicMock()
    client._last_id = 41
    client._paths = {41: Path("/tmp/first.png")}
    client.proxy.call_sync.side_effect = [None, GLib.Variant("(u)", (42,))]
    client.show(Path("/tmp/second.png"), 100, 50)
    assert client.proxy.call_sync.call_args_list[0].args[0] == "CloseNotification"
    assert client.proxy.call_sync.call_args_list[1].args[0] == "Notify"
    notify_args = client.proxy.call_sync.call_args_list[1].args[1].unpack()
    assert notify_args[1] == 0  # Never replace the previous notification/history item.
    assert client._last_id == 42
    assert 41 not in client._paths


def test_default_action_reveals_current_file(monkeypatch) -> None:
    client = ScreenshotNotifications.__new__(ScreenshotNotifications)
    client._last_id = 7
    client._paths = {7: Path("/tmp/shot.png")}
    shown = []
    monkeypatch.setattr(client, "_show_item", shown.append)
    client._on_signal(None, "", "ActionInvoked", GLib.Variant("(us)", (7, "default")))
    assert shown == [Path("/tmp/shot.png")]
