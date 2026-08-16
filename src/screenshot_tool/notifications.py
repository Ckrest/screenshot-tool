"""Freedesktop notification client with no notification-server-specific API."""

from __future__ import annotations

import logging
from pathlib import Path

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)


class ScreenshotNotifications:
    """Keep only the latest screenshot popup visible while creating distinct notifications."""

    BUS = "org.freedesktop.Notifications"
    PATH = "/org/freedesktop/Notifications"
    INTERFACE = "org.freedesktop.Notifications"

    def __init__(self) -> None:
        self._last_id = 0
        self._paths: dict[int, Path] = {}
        try:
            self.proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.NONE,
                None,
                self.BUS,
                self.PATH,
                self.INTERFACE,
                None,
            )
            self.proxy.connect("g-signal", self._on_signal)
        except GLib.Error as exc:
            log.debug("Notification service unavailable: %s", exc)
            self.proxy = None

    def show(self, path: Path, width: int, height: int) -> None:
        if self.proxy is None:
            return
        try:
            if self._last_id:
                self.proxy.call_sync(
                    "CloseNotification",
                    GLib.Variant("(u)", (self._last_id,)),
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None,
                )
                self._paths.pop(self._last_id, None)
                self._last_id = 0
            hints = {
                "desktop-entry": GLib.Variant("s", "org.nick.ScreenshotTool"),
                "urgency": GLib.Variant("y", 0),
                "category": GLib.Variant("s", "transfer.complete"),
            }
            reply = self.proxy.call_sync(
                "Notify",
                GLib.Variant(
                    "(susssasa{sv}i)",
                    (
                        "Screenshot Tool",
                        0,
                        "org.nick.ScreenshotTool",
                        "Screenshot Captured",
                        f"{path.name}\n{width}×{height} pixels",
                        ["default", "Show in Files"],
                        hints,
                        10000,
                    ),
                ),
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
            self._last_id = reply.unpack()[0]
            self._paths[self._last_id] = path
        except GLib.Error as exc:
            log.debug("Could not publish screenshot notification: %s", exc)

    def _on_signal(
        self, _proxy, _sender: str, signal: str, parameters: GLib.Variant
    ) -> None:
        values = parameters.unpack()
        if signal == "NotificationClosed":
            notification_id = values[0]
            self._paths.pop(notification_id, None)
            if notification_id == self._last_id:
                self._last_id = 0
        elif signal == "ActionInvoked":
            notification_id, action = values
            path = self._paths.get(notification_id)
            if path and action == "default":
                self._show_item(path)

    @staticmethod
    def _show_item(path: Path) -> None:
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            connection.call_sync(
                "org.freedesktop.FileManager1",
                "/org/freedesktop/FileManager1",
                "org.freedesktop.FileManager1",
                "ShowItems",
                GLib.Variant("(ass)", ([path.resolve().as_uri()], "")),
                None,
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
        except GLib.Error as exc:
            log.debug("Could not reveal screenshot: %s", exc)
