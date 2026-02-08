"""Main screenshot overlay window."""

import logging
import os
import signal
import tempfile
from pathlib import Path
from typing import Optional

import cairo
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, GtkLayerShell

from ..config import Config, get_config
from ..capture import fullscreen as capture_fullscreen, window as capture_window
from ..output import OutputOptions, save, save_pixbuf
from ..wayfire import (
    get_cursor_position,
    get_window_geometries,
    hide_cursor,
    show_cursor,
    focus_screenshot_tool,
)
from .drawing import (
    draw_crosshair,
    draw_dimension_text,
    draw_instructions,
    draw_selection_overlay,
    draw_window_highlight,
)
from .magnifier import Magnifier

log = logging.getLogger(__name__)

# Global instance for signal handler
_overlay_instance: Optional["ScreenshotOverlay"] = None


def _glib_signal_handler():
    """Handle SIGUSR1 via GLib for GTK compatibility."""
    global _overlay_instance
    if _overlay_instance:
        GLib.idle_add(_overlay_instance.take_fullscreen_now)
    return True  # Keep handler active


class ScreenshotOverlay(Gtk.Window):
    """Full-screen overlay for interactive screenshot capture."""

    def __init__(self, config: Optional[Config] = None):
        super().__init__(title="Screenshot Tool")
        self.config = config or get_config()

        # Store global instance for signal handling
        global _overlay_instance
        _overlay_instance = self

        # Setup as layer-shell overlay (must be done BEFORE window is realized)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_exclusive_zone(self, -1)  # Cover entire screen
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)

        # Get window geometries BEFORE capturing (for window selection)
        self.windows = get_window_geometries()
        log.debug("Got %d windows", len(self.windows))

        # Capture the current screen BEFORE showing window
        self._temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        self._temp_file.close()
        try:
            temp_path = capture_fullscreen(config=self.config)
            # Move to our temp file location
            temp_path.rename(self._temp_file.name)
        except Exception as e:
            log.error("Failed to capture screen: %s", e)
            raise

        # Load the screenshot
        self.screenshot = GdkPixbuf.Pixbuf.new_from_file(self._temp_file.name)
        self.img_width = self.screenshot.get_width()
        self.img_height = self.screenshot.get_height()
        log.debug("Screenshot loaded: %dx%d", self.img_width, self.img_height)

        # Window setup
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)

        # Drawing area
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self._on_draw)
        self.add(self.drawing_area)

        # Selection state
        self.selecting = False
        self.start_x: Optional[float] = None
        self.start_y: Optional[float] = None
        self.end_x: Optional[float] = None
        self.end_y: Optional[float] = None
        self.hovered_window: Optional[dict] = None

        # Get initial cursor position
        cursor_pos = get_cursor_position()
        if cursor_pos and 0 <= cursor_pos[0] < self.img_width and 0 <= cursor_pos[1] < self.img_height:
            self.current_x = float(cursor_pos[0])
            self.current_y = float(cursor_pos[1])
        else:
            self.current_x = float(self.img_width // 2)
            self.current_y = float(self.img_height // 2)

        # Mouse events
        self.drawing_area.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )

        self.drawing_area.connect("button-press-event", self._on_button_press)
        self.drawing_area.connect("button-release-event", self._on_button_release)
        self.drawing_area.connect("motion-notify-event", self._on_motion)
        self.connect("key-press-event", self._on_key_press)

        # Make widget focusable
        self.drawing_area.set_can_focus(True)
        self.drawing_area.grab_focus()

        # Magnifier
        self.magnifier = Magnifier()

        self.show_all()

        # Hide the cursor after window is shown
        GLib.idle_add(self._hide_cursor_and_redraw)

    def _hide_cursor_and_redraw(self):
        """Hide the system cursor over the window."""
        window = self.get_window()
        if window:
            display = window.get_display()
            blank_cursor = Gdk.Cursor.new_for_display(display, Gdk.CursorType.BLANK_CURSOR)
            window.set_cursor(blank_cursor)
        self.drawing_area.queue_draw()
        return False

    def _find_window_at(self, x: float, y: float) -> Optional[dict]:
        """Find the topmost window containing the given coordinates."""
        for window in self.windows:
            wx = window.get("x", 0)
            wy = window.get("y", 0)
            ww = window.get("width", 0)
            wh = window.get("height", 0)
            if wx <= x < wx + ww and wy <= y < wy + wh:
                return window
        return None

    def _on_draw(self, widget, cr):
        # Draw the frozen screenshot
        Gdk.cairo_set_source_pixbuf(cr, self.screenshot, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()

        # Highlight hovered window if not dragging
        if not self.selecting and self.hovered_window:
            draw_window_highlight(cr, self.hovered_window, self.windows, self.screenshot)

        # Draw selection rectangle if dragging
        if self.selecting and self.start_x is not None:
            x = int(min(self.start_x, self.current_x))
            y = int(min(self.start_y, self.current_y))
            w = int(abs(self.current_x - self.start_x))
            h = int(abs(self.current_y - self.start_y))

            draw_selection_overlay(cr, x, y, w, h, self.img_width, self.img_height)
            draw_dimension_text(cr, x, y, w, h)

        # Draw magnifier and crosshair
        self.magnifier.draw(
            cr, self.current_x, self.current_y,
            self.screenshot, self.img_width, self.img_height
        )
        draw_crosshair(cr, self.current_x, self.current_y)

        # Draw instructions
        draw_instructions(cr)

        return False

    def _on_button_press(self, widget, event):
        if event.button == 3:  # Right-click cancels
            self._cleanup_and_exit()
            return True

        if event.button == 1:  # Left-click starts selection
            self.selecting = True
            self.start_x = self.current_x
            self.start_y = self.current_y
            widget.queue_draw()
        return True

    def _on_button_release(self, widget, event):
        if event.button != 1:
            return True

        self.selecting = False
        self.end_x = self.current_x
        self.end_y = self.current_y

        drag_threshold = 5
        if (
            abs(self.end_x - self.start_x) < drag_threshold
            and abs(self.end_y - self.start_y) < drag_threshold
        ):
            # Click - check if on a window
            if self.hovered_window:
                self._take_window_screenshot(self.hovered_window)
            else:
                # No window, take full screen
                self._take_screenshot(0, 0, self.img_width, self.img_height)
        else:
            # Drag selection
            x = int(min(self.start_x, self.end_x))
            y = int(min(self.start_y, self.end_y))
            w = int(abs(self.end_x - self.start_x))
            h = int(abs(self.end_y - self.start_y))
            if w > 0 and h > 0:
                self._take_screenshot(x, y, w, h)

        return True

    def _on_motion(self, widget, event):
        self.current_x = event.x
        self.current_y = event.y

        if not self.selecting:
            self.hovered_window = self._find_window_at(self.current_x, self.current_y)

        widget.queue_draw()
        return True

    def _on_key_press(self, widget, event):
        # Arrow keys for fine adjustment
        moved = False
        if event.keyval == Gdk.KEY_Left:
            self.current_x = max(0, self.current_x - 1)
            moved = True
        elif event.keyval == Gdk.KEY_Right:
            self.current_x = min(self.img_width, self.current_x + 1)
            moved = True
        elif event.keyval == Gdk.KEY_Up:
            self.current_y = max(0, self.current_y - 1)
            moved = True
        elif event.keyval == Gdk.KEY_Down:
            self.current_y = min(self.img_height, self.current_y + 1)
            moved = True

        if moved:
            if not self.selecting:
                self.hovered_window = self._find_window_at(self.current_x, self.current_y)
            widget.queue_draw()
            return True

        # Cancel
        if event.keyval == Gdk.KEY_Escape:
            self._cleanup_and_exit()
            return True

        # Full screen capture (PrintScreen, Space, SysReq)
        KEY_SYSRQ = 65301
        if event.keyval in (Gdk.KEY_Print, Gdk.KEY_space, KEY_SYSRQ):
            self._take_screenshot(0, 0, self.img_width, self.img_height)
            return True

        # Confirm selection with Enter
        if event.keyval == Gdk.KEY_Return and self.selecting:
            x = int(min(self.start_x, self.current_x))
            y = int(min(self.start_y, self.current_y))
            w = int(abs(self.current_x - self.start_x))
            h = int(abs(self.current_y - self.start_y))
            if w > 0 and h > 0:
                self._take_screenshot(x, y, w, h)
            return True

        return True

    def take_fullscreen_now(self):
        """Take full screen screenshot immediately (for signal handler)."""
        self._take_screenshot(0, 0, self.img_width, self.img_height)

    def _take_window_screenshot(self, window: dict):
        """Capture a specific window."""
        try:
            app_id = window.get("app_id", "")
            if not app_id:
                log.error("Window has no app_id")
                return

            temp_path = capture_window(app_id, config=self.config)
            save(temp_path, OutputOptions(), self.config)
            temp_path.unlink(missing_ok=True)
        except Exception as e:
            log.error("Error capturing window: %s", e)
        finally:
            self._cleanup_and_exit()

    def _take_screenshot(self, x: int, y: int, w: int, h: int):
        """Capture a region of the frozen screenshot."""
        try:
            cropped = self.screenshot.new_subpixbuf(x, y, w, h)
            save_pixbuf(cropped, OutputOptions(), self.config)
        except Exception as e:
            log.error("Error saving screenshot: %s", e)
        finally:
            self._cleanup_and_exit()

    def _cleanup_and_exit(self):
        """Clean up and close the overlay."""
        global _overlay_instance
        _overlay_instance = None

        try:
            os.unlink(self._temp_file.name)
        except OSError:
            pass

        self.hide()
        self.destroy()
        Gtk.main_quit()


def run_interactive(config: Optional[Config] = None) -> int:
    """Run the interactive screenshot overlay.

    Args:
        config: Configuration object

    Returns:
        Exit code (0 for success)
    """
    config = config or get_config()

    # Set app_id for Wayland (must be done before GTK init)
    os.environ["GDK_BACKEND"] = "wayland"
    GLib.set_prgname("screenshot-tool")
    GLib.set_application_name("Screenshot Tool")

    # Set up signal handler for SIGUSR1 (fullscreen trigger from another invocation)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGUSR1, _glib_signal_handler)

    # Hide cursor before showing overlay
    hide_cursor()

    try:
        ScreenshotOverlay(config)
        Gtk.main()
    finally:
        show_cursor()

    return 0
