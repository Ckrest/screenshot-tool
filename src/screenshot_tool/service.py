"""Persistent GTK4/D-Bus screenshot service and capture state machine."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, ClassVar

import gi

gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

from .backend import CaptureError, WaylandCaptureBackend
from .config import Config, load_config
from .dbus_api import APP_ID, INTERFACE, OBJECT_PATH
from .models import CaptureRequest, OutputResult, RawFrame, Rect
from .notifications import ScreenshotNotifications
from .output import copy_to_clipboard, options_for_request, save_frame
from .post_save_hooks import notify_save, play_sound
from .ui import ScreenshotOverlay
from .window import Window, enumerate_windows, find_window_by_app_id

log = logging.getLogger(__name__)

INTROSPECTION_XML = f"""
<node>
  <interface name="{INTERFACE}">
    <method name="Request"><arg name="options" type="a{{sv}}" direction="in"/><arg name="request_id" type="s" direction="out"/></method>
    <method name="Cancel"><arg name="request_id" type="s" direction="in"/><arg name="cancelled" type="b" direction="out"/></method>
    <method name="GetState"><arg name="state" type="a{{sv}}" direction="out"/></method>
    <signal name="Completed"><arg name="request_id" type="s"/><arg name="result" type="a{{sv}}"/></signal>
    <signal name="Failed"><arg name="request_id" type="s"/><arg name="code" type="s"/><arg name="message" type="s"/></signal>
  </interface>
</node>
"""


def _variant_map(values: dict[str, Any]) -> dict[str, GLib.Variant]:
    result: dict[str, GLib.Variant] = {}
    for key, value in values.items():
        if isinstance(value, bool):
            result[key] = GLib.Variant("b", value)
        elif isinstance(value, int):
            result[key] = GLib.Variant("x", value)
        else:
            result[key] = GLib.Variant("s", str(value))
    return result


class ScreenshotController:
    STATES: ClassVar = {"idle", "freezing", "selecting", "saving"}

    def __init__(
        self, application: Gtk.Application, emit: Callable[[str, GLib.Variant], None]
    ) -> None:
        self.application = application
        self.emit = emit
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="screenshot-tool"
        )
        self.notifications = ScreenshotNotifications()
        self.state = "idle"
        self.request: CaptureRequest | None = None
        self.participants: list[str] = []
        self.frame: RawFrame | None = None
        self.windows: list[Window] = []
        self.overlay: ScreenshotOverlay | None = None
        self.config: Config | None = None
        self._generation = 0
        self._force_fullscreen = False

    def request_capture(self, request: CaptureRequest) -> None:
        if request.mode not in {"interactive", "fullscreen", "region", "window"}:
            self._emit_failed(
                request.request_id, "InvalidRequest", f"Unknown mode: {request.mode}"
            )
            return
        if request.mode == "region" and request.region is None:
            self._emit_failed(
                request.request_id, "InvalidRequest", "Region capture requires X,Y,W,H"
            )
            return
        if request.mode == "window" and not request.window_app_id:
            self._emit_failed(
                request.request_id,
                "InvalidRequest",
                "Window capture requires an app-id",
            )
            return

        if (
            request.mode == "interactive"
            and self.state in {"freezing", "selecting"}
            and self.request
            and self.request.mode == "interactive"
        ):
            self.participants.append(request.request_id)
            self._force_fullscreen = True
            if self.state == "selecting" and self.overlay:
                self.overlay.confirm_fullscreen()
            return
        if self.state != "idle":
            self._emit_failed(
                request.request_id, "Busy", f"Screenshot Tool is {self.state}"
            )
            return

        self._generation += 1
        self.request = request
        self.participants = [request.request_id]
        self.config = load_config(request.config_path)
        self._force_fullscreen = False
        self._set_state("freezing")
        generation = self._generation
        if request.mode == "window":
            self._submit(generation, self._capture_named_window, self.config, request)
        else:
            self._submit(generation, self._capture_desktop, self.config, request)

    @staticmethod
    def _capture_desktop(
        config: Config, request: CaptureRequest
    ) -> tuple[RawFrame, list[Window], Window | None]:
        frame = WaylandCaptureBackend(config).capture_desktop(
            request.monitor, request.delay_ms
        )
        windows = (
            [item.mapped_to_frame(frame) for item in enumerate_windows(config)]
            if request.mode == "interactive"
            else []
        )
        return frame, windows, None

    @staticmethod
    def _capture_named_window(
        config: Config, request: CaptureRequest
    ) -> tuple[RawFrame, list[Window], Window | None]:
        target = find_window_by_app_id(request.window_app_id or "", config)
        if target is None:
            raise CaptureError(f"Window not found: {request.window_app_id}")
        frame = WaylandCaptureBackend(config).capture_window(
            target.capture_id, request.delay_ms
        )
        return frame, [], target

    def _submit(self, generation: int, function: Callable, *args) -> None:
        future = self.executor.submit(function, *args)
        future.add_done_callback(
            lambda item: GLib.idle_add(self._worker_finished, generation, item)
        )

    def _worker_finished(self, generation: int, future: Future) -> bool:
        if generation != self._generation:
            return GLib.SOURCE_REMOVE
        try:
            value = future.result()
        except Exception as exc:  # noqa: BLE001 - worker boundaries normalize all failures.
            self._fail_active("CaptureFailed", str(exc))
            return GLib.SOURCE_REMOVE
        if isinstance(value, OutputResult):
            self._complete(value)
            return GLib.SOURCE_REMOVE
        frame, windows, target = value
        self.frame, self.windows = frame, windows
        assert self.request is not None
        if (
            self.request.mode == "interactive"
            and self.state == "saving"
            and target is not None
        ):
            self._save(frame, "window", target)
        elif self.request.mode == "interactive" and not self._force_fullscreen:
            self._show_overlay()
        elif self.request.mode == "region":
            self._save(
                frame.crop(
                    frame.logical_rect_to_frame(self.request.region)
                    if self.request.region
                    else Rect(0, 0, frame.width, frame.height)
                ),
                "region",
            )
        elif self.request.mode == "window":
            self._save(frame, "window", target)
        else:
            self._save(frame, "fullscreen")
        return GLib.SOURCE_REMOVE

    def _show_overlay(self) -> None:
        assert self.frame is not None and self.request is not None
        self._set_state("selecting")
        self.overlay = ScreenshotOverlay(
            self.application,
            self.frame,
            self.windows,
            self._select_region,
            self._select_window,
            self._select_fullscreen,
            self._cancel_active,
            self.request.monitor,
        )
        self.overlay.show()

    def _select_region(self, rect: Rect) -> None:
        self.overlay = None
        assert self.frame is not None
        try:
            frame = self.frame.crop(rect)
        except ValueError as exc:
            self._fail_active("InvalidRegion", str(exc))
            return
        self._save(frame, "region")

    def _select_window(self, window: Window) -> None:
        self.overlay = None
        assert self.config is not None
        self._set_state("saving")
        generation = self._generation
        self._submit(generation, self._capture_selected_window, self.config, window)

    @staticmethod
    def _capture_selected_window(
        config: Config, window: Window
    ) -> tuple[RawFrame, list[Window], Window | None]:
        return (
            WaylandCaptureBackend(config).capture_window(window.capture_id),
            [],
            window,
        )

    def _select_fullscreen(self) -> None:
        self.overlay = None
        assert self.frame is not None
        self._save(self.frame, "fullscreen")

    def _save(self, frame: RawFrame, source: str, window: Window | None = None) -> None:
        assert self.request is not None and self.config is not None
        self._set_state("saving")
        options = options_for_request(self.request, self.config)
        config, request = self.config, self.request

        def work() -> OutputResult:
            result = save_frame(
                frame,
                options,
                config,
                source,
                window.app_id if window else request.window_app_id,
                window.title if window else None,
            )
            if options.clipboard:
                copy_to_clipboard(result.path, options.output_format)
            return result

        self._submit(self._generation, work)

    def _complete(self, result: OutputResult) -> None:
        assert self.request is not None and self.config is not None
        options = options_for_request(self.request, self.config)
        if options.sound:
            play_sound()
        if options.notification:
            self.notifications.show(result.path, result.width, result.height)
        notify_save(result, self.config.hooks_dir)
        payload = _variant_map(result.to_dict())
        for request_id in self.participants:
            self.emit("Completed", GLib.Variant("(sa{sv})", (request_id, payload)))
        self._reset()

    def cancel(self, request_id: str) -> bool:
        if request_id not in self.participants:
            return False
        if self.overlay:
            self.overlay.cancel()
        else:
            self._cancel_active()
        return True

    def _cancel_active(self) -> None:
        self._generation += 1
        for request_id in self.participants:
            self._emit_failed(request_id, "Cancelled", "Screenshot cancelled")
        self._reset()

    def _fail_active(self, code: str, message: str) -> None:
        for request_id in self.participants:
            self._emit_failed(request_id, code, message)
        self._reset()

    def _emit_failed(self, request_id: str, code: str, message: str) -> None:
        self.emit("Failed", GLib.Variant("(sss)", (request_id, code, message)))

    def _set_state(self, state: str) -> None:
        assert state in self.STATES
        self.state = state

    def _reset(self) -> None:
        self.state = "idle"
        self.request = None
        self.participants = []
        self.frame = None
        self.windows = []
        self.overlay = None
        self.config = None
        self._force_fullscreen = False

    def state_map(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "active_request": self.participants[0] if self.participants else "",
            "force_fullscreen": self._force_fullscreen,
        }


class ScreenshotService(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.IS_SERVICE)
        self.registration_id = 0
        self.controller: ScreenshotController | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        self.hold()
        connection = self.get_dbus_connection()
        interface = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML).interfaces[0]
        self.registration_id = connection.register_object(
            OBJECT_PATH, interface, self._method_call, None, None
        )
        self.controller = ScreenshotController(self, self._emit)
        log.info("Screenshot Tool service ready")

    def do_activate(self) -> None:
        pass

    def do_shutdown(self) -> None:
        if self.controller:
            self.controller.executor.shutdown(wait=False, cancel_futures=True)
        if self.registration_id:
            self.get_dbus_connection().unregister_object(self.registration_id)
        Gtk.Application.do_shutdown(self)

    def _emit(self, name: str, parameters: GLib.Variant) -> None:
        self.get_dbus_connection().emit_signal(
            None, OBJECT_PATH, INTERFACE, name, parameters
        )

    def _method_call(
        self, _connection, _sender, _path, _interface, method, parameters, invocation
    ) -> None:
        assert self.controller is not None
        try:
            if method == "Request":
                values = parameters.unpack()[0]
                request = CaptureRequest.from_mapping(values)
                invocation.return_value(GLib.Variant("(s)", (request.request_id,)))
                self.controller.request_capture(request)
            elif method == "Cancel":
                invocation.return_value(
                    GLib.Variant(
                        "(b)", (self.controller.cancel(parameters.unpack()[0]),)
                    )
                )
            elif method == "GetState":
                invocation.return_value(
                    GLib.Variant(
                        "(a{sv})", (_variant_map(self.controller.state_map()),)
                    )
                )
        except Exception as exc:  # noqa: BLE001 - D-Bus callers must receive a typed error.
            invocation.return_dbus_error(f"{INTERFACE}.Error", str(exc))


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    return ScreenshotService().run([])
