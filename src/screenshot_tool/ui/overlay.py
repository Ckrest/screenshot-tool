"""GTK4 frozen-frame selector spanning every captured output."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Gtk4LayerShell

from ..models import CoordinateMapper, OutputLayout, RawFrame, Rect, SelectionModel
from ..wayfire import get_cursor_position
from ..window import Window
from .drawing import OverlayDrawing

INSTRUCTION_DISMISS_DISTANCE = 72


def point_near_rectangle(
    x: float,
    y: float,
    left: float,
    top: float,
    width: float,
    height: float,
    distance: float = INSTRUCTION_DISMISS_DISTANCE,
) -> bool:
    return (
        left - distance <= x <= left + width + distance
        and top - distance <= y <= top + height + distance
    )


class _OverlayView:
    """One output-local surface into the shared frozen-frame model."""

    def __init__(
        self,
        owner: ScreenshotOverlay,
        application: Gtk.Application,
        output: OutputLayout,
        primary: bool,
    ) -> None:
        self.owner = owner
        self.output = output
        self.mapper = CoordinateMapper(
            owner.frame.width, owner.frame.height, output.frame_rect
        )
        viewport = owner.frame.crop(output.frame_rect)
        byte_data = GLib.Bytes.new(viewport.pixels)
        texture = Gdk.MemoryTexture.new(
            viewport.width,
            viewport.height,
            Gdk.MemoryFormat.R8G8B8A8,
            byte_data,
            viewport.stride,
        )

        self.window = Gtk.ApplicationWindow(application=application)
        self.window.set_title("Screenshot Tool")
        self.window.set_decorated(False)
        Gtk4LayerShell.init_for_window(self.window)
        Gtk4LayerShell.set_namespace(self.window, "screenshot-tool")
        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_keyboard_mode(
            self.window,
            Gtk4LayerShell.KeyboardMode.EXCLUSIVE
            if primary
            else Gtk4LayerShell.KeyboardMode.NONE,
        )
        Gtk4LayerShell.set_exclusive_zone(self.window, -1)
        for edge in (
            Gtk4LayerShell.Edge.TOP,
            Gtk4LayerShell.Edge.BOTTOM,
            Gtk4LayerShell.Edge.LEFT,
            Gtk4LayerShell.Edge.RIGHT,
        ):
            Gtk4LayerShell.set_anchor(self.window, edge, True)
        self._select_monitor(output.name)
        if hasattr(self.window, "set_cursor_from_name"):
            self.window.set_cursor_from_name("none")

        overlay = Gtk.Overlay()
        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_can_shrink(True)
        picture.set_content_fit(Gtk.ContentFit.FILL)
        overlay.set_child(picture)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_hexpand(True)
        self.canvas.set_vexpand(True)
        self.drawing = OverlayDrawing(
            owner.model, self.mapper, owner.pixbuf, owner.windows
        )
        self.canvas.set_draw_func(self.drawing.draw)
        overlay.add_overlay(self.canvas)
        self.instructions: Gtk.Label | None = None
        if primary:
            instructions = Gtk.Label(
                label=(
                    "Drag a region  •  Click a window  •  "
                    "Space: fullscreen  •  Esc: cancel"
                )
            )
            instructions.set_halign(Gtk.Align.CENTER)
            instructions.set_valign(Gtk.Align.START)
            instructions.set_margin_top(28)
            # The canvas owns all pointer interaction. Keep this visual hint out
            # of GTK's pick path so motion and clicks continue underneath it.
            instructions.set_can_target(False)
            instructions.add_css_class("screenshot-instructions")
            overlay.add_overlay(instructions)
            self.instructions = instructions
        self.window.set_child(overlay)
        self._install_controllers()

    def _select_monitor(self, connector: str) -> None:
        monitors = self.window.get_display().get_monitors()
        for index in range(monitors.get_n_items()):
            monitor = monitors.get_item(index)
            if monitor.get_connector() == connector:
                Gtk4LayerShell.set_monitor(self.window, monitor)
                return

    def _install_controllers(self) -> None:
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.owner._motion, self)
        self.canvas.add_controller(motion)
        primary = Gtk.GestureClick(button=1)
        primary.connect("pressed", self.owner._pressed, self)
        primary.connect("released", self.owner._released, self)
        self.canvas.add_controller(primary)
        secondary = Gtk.GestureClick(button=3)
        secondary.connect("pressed", lambda *_args: self.owner.cancel())
        self.canvas.add_controller(secondary)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.owner._key_pressed)
        self.window.add_controller(keys)

    def present(self) -> None:
        self.window.present()

    def queue_draw(self) -> None:
        self.canvas.queue_draw()

    def hide_instructions(self) -> None:
        if self.instructions is not None:
            self.instructions.set_visible(False)

    def pointer_near_instructions(self, x: float, y: float) -> bool:
        if self.instructions is None or not self.instructions.get_visible():
            return False
        allocation = self.instructions.get_allocation()
        return point_near_rectangle(
            x,
            y,
            allocation.x,
            allocation.y,
            allocation.width,
            allocation.height,
        )

    def destroy(self) -> None:
        self.window.set_visible(False)
        self.window.destroy()


class ScreenshotOverlay:
    def __init__(
        self,
        application: Gtk.Application,
        frame: RawFrame,
        windows: list[Window],
        on_region: Callable[[Rect], None],
        on_window: Callable[[Window], None],
        on_fullscreen: Callable[[], None],
        on_cancel: Callable[[], None],
        monitor: str | None = None,
    ) -> None:
        self.frame = frame
        self.windows = windows
        self.on_region, self.on_window = on_region, on_window
        self.on_fullscreen, self.on_cancel = on_fullscreen, on_cancel
        self._finished = False
        cursor = get_cursor_position()
        initial = (
            frame.logical_point_to_frame(*cursor)
            if cursor is not None
            else (frame.width // 2, frame.height // 2)
        )
        self.model = SelectionModel(frame.width, frame.height, initial)
        byte_data = GLib.Bytes.new(frame.pixels)
        self.pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            byte_data,
            GdkPixbuf.Colorspace.RGB,
            True,
            8,
            frame.width,
            frame.height,
            frame.stride,
        )
        layouts = list(frame.outputs)
        if monitor:
            layouts = [item for item in layouts if item.name == monitor]
        if not layouts:
            layouts = [
                OutputLayout(
                    name=monitor or frame.output_name or "",
                    logical_x=frame.logical_origin[0],
                    logical_y=frame.logical_origin[1],
                    logical_width=frame.width,
                    logical_height=frame.height,
                    buffer_width=frame.width,
                    buffer_height=frame.height,
                    scale=1.0,
                    transform="normal",
                    frame_x=0,
                    frame_y=0,
                    frame_width=frame.width,
                    frame_height=frame.height,
                )
            ]
        self._install_css()
        self._instructions_visible = True
        self.views = [
            _OverlayView(self, application, output, index == 0)
            for index, output in enumerate(layouts)
        ]

    @staticmethod
    def _install_css() -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b".screenshot-instructions { background: rgba(15,18,24,.9); color: white; padding: 10px 16px; border-radius: 8px; font-weight: 600; }"
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def show(self) -> None:
        for view in self.views:
            view.present()

    def _queue_draw(self) -> None:
        for view in self.views:
            view.queue_draw()

    def _move_from_widget(self, view: _OverlayView, x: float, y: float) -> None:
        self.model.move(
            *view.mapper.widget_to_frame(
                x, y, view.canvas.get_width(), view.canvas.get_height()
            )
        )
        self._queue_draw()

    def _motion(self, _controller, x: float, y: float, view: _OverlayView) -> None:
        self._dismiss_instructions_near(view, x, y)
        self._move_from_widget(view, x, y)

    def _pressed(
        self, _gesture, _count: int, x: float, y: float, view: _OverlayView
    ) -> None:
        self._dismiss_instructions_near(view, x, y)
        self._move_from_widget(view, x, y)
        self.model.begin()

    def _dismiss_instructions_near(
        self, view: _OverlayView, x: float, y: float
    ) -> None:
        if self._instructions_visible and view.pointer_near_instructions(x, y):
            self._dismiss_instructions()

    def _dismiss_instructions(self) -> None:
        if not self._instructions_visible:
            return
        self._instructions_visible = False
        for view in self.views:
            view.hide_instructions()

    def _released(
        self, _gesture, _count: int, x: float, y: float, view: _OverlayView
    ) -> None:
        self._move_from_widget(view, x, y)
        selection = self.model.selection
        if selection and selection.width >= 4 and selection.height >= 4:
            self._finish(lambda: self.on_region(selection))
            return
        self.model.clear()
        target = view.drawing.hovered_window()
        if target and target.capture_id:
            self._finish(lambda: self.on_window(target))
        else:
            self._queue_draw()

    def _key_pressed(self, _controller, keyval: int, _keycode: int, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.cancel()
        elif keyval in {Gdk.KEY_space, Gdk.KEY_Print, Gdk.KEY_KP_Space}:
            self.confirm_fullscreen()
        elif keyval in {Gdk.KEY_Return, Gdk.KEY_KP_Enter}:
            selection = self.model.selection
            target = next(
                (view.drawing.hovered_window() for view in self.views), None
            )
            if selection and selection.width and selection.height:
                self._finish(lambda: self.on_region(selection))
            elif target and target.capture_id:
                self._finish(lambda: self.on_window(target))
        elif keyval in {Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down}:
            self.model.nudge(
                -1 if keyval == Gdk.KEY_Left else 1 if keyval == Gdk.KEY_Right else 0,
                -1 if keyval == Gdk.KEY_Up else 1 if keyval == Gdk.KEY_Down else 0,
            )
            self._queue_draw()
        else:
            return False
        return True

    def confirm_fullscreen(self) -> None:
        self._finish(self.on_fullscreen)

    def cancel(self) -> None:
        self._finish(self.on_cancel)

    def _finish(self, callback: Callable[[], None]) -> None:
        if self._finished:
            return
        self._finished = True
        for view in self.views:
            view.destroy()
        callback()
