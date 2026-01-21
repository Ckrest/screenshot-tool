"""Optional Wayfire IPC integration.

All functions gracefully degrade if Wayfire is not available.
This module handles:
- Cursor visibility (hide/show via cursor-control plugin)
- Window geometry retrieval (for window selection)
- Cursor position (for initial magnifier placement)
- Window focusing (to bring screenshot-tool to front)
"""

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


def _get_socket():
    """Get a Wayfire IPC socket, or None if unavailable."""
    try:
        from wayfire import WayfireSocket
        sock = WayfireSocket()
        sock.client.settimeout(1.0)
        return sock
    except Exception as e:
        log.debug("Wayfire IPC unavailable: %s", e)
        return None


def is_cursor_hidden() -> bool:
    """Check if cursor is currently hidden."""
    sock = _get_socket()
    if not sock:
        return False

    try:
        msg = json.dumps({"method": "cursor-control/is-hidden", "data": {}}).encode("utf8")
        sock.client.send(len(msg).to_bytes(4, byteorder="little") + msg)
        result = sock.read_message()
        return result.get("hidden", False)
    except Exception as e:
        log.debug("Could not check cursor state: %s", e)
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def hide_cursor() -> bool:
    """Hide cursor using Wayfire cursor-control plugin.

    Returns:
        True if cursor was hidden, False if operation failed
    """
    sock = _get_socket()
    if not sock:
        return False

    try:
        # Check if already hidden
        msg = json.dumps({"method": "cursor-control/is-hidden", "data": {}}).encode("utf8")
        sock.client.send(len(msg).to_bytes(4, byteorder="little") + msg)
        result = sock.read_message()
        if result.get("hidden", False):
            return True  # Already hidden

        # Hide it
        msg = json.dumps({"method": "cursor-control/hide", "data": {}}).encode("utf8")
        sock.client.send(len(msg).to_bytes(4, byteorder="little") + msg)
        sock.read_message()
        return True
    except Exception as e:
        log.warning("Could not hide cursor via IPC: %s", e)
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def show_cursor() -> bool:
    """Show cursor using Wayfire cursor-control plugin.

    Returns:
        True if cursor was shown, False if operation failed
    """
    sock = _get_socket()
    if not sock:
        return False

    try:
        msg = json.dumps({"method": "cursor-control/show", "data": {}}).encode("utf8")
        sock.client.send(len(msg).to_bytes(4, byteorder="little") + msg)
        sock.read_message()
        return True
    except Exception as e:
        log.warning("Could not show cursor via IPC: %s", e)
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def get_cursor_position() -> Optional[tuple[int, int]]:
    """Get current cursor position.

    Returns:
        (x, y) tuple or None if unavailable
    """
    sock = _get_socket()
    if not sock:
        return None

    try:
        cursor_pos = sock.get_cursor_position()
        return (int(cursor_pos[0]), int(cursor_pos[1]))
    except Exception as e:
        log.debug("Could not get cursor position: %s", e)
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass


def get_window_geometries() -> list[dict]:
    """Get window positions sorted by z-order (front to back).

    Returns:
        List of window dicts with keys:
        - id: Wayfire view ID
        - title: Window title
        - app_id: Wayland app-id
        - x, y, width, height: Geometry
        - focus_timestamp: Last focus time (for z-order)
        - z_order: Index in z-order (0 = front)
    """
    sock = _get_socket()
    if not sock:
        return []

    windows = []
    try:
        views = sock.list_views()

        for view in views:
            app_id = view.get("app-id", "")
            # Only include mapped, non-minimized, toplevel windows on workspace
            # Skip screenshot-tool itself
            if (
                view.get("mapped", False)
                and not view.get("minimized", False)
                and view.get("type") == "toplevel"
                and view.get("layer") == "workspace"
                and app_id != "screenshot-tool"
                and app_id
            ):
                geo = view.get("geometry", {})
                if geo.get("width", 0) > 0 and geo.get("height", 0) > 0:
                    windows.append({
                        "id": view.get("id"),
                        "title": view.get("title", "Unknown"),
                        "app_id": app_id,
                        "x": geo.get("x", 0),
                        "y": geo.get("y", 0),
                        "width": geo.get("width", 0),
                        "height": geo.get("height", 0),
                        "focus_timestamp": view.get("last-focus-timestamp", 0),
                    })

        # Sort by focus timestamp descending (most recently focused = front)
        windows.sort(key=lambda w: w["focus_timestamp"], reverse=True)

        # Assign z_order after sorting
        for i, window in enumerate(windows):
            window["z_order"] = i

    except Exception as e:
        log.warning("Could not get window geometries: %s", e)

    finally:
        try:
            sock.close()
        except Exception:
            pass

    return windows


def focus_screenshot_tool() -> bool:
    """Focus the screenshot-tool window to bring it to front.

    Returns:
        True if focus was set, False if operation failed
    """
    sock = _get_socket()
    if not sock:
        return False

    try:
        views = sock.list_views()
        for view in views:
            if view.get("app-id") == "screenshot-tool":
                view_id = view.get("id")
                msg = json.dumps({
                    "method": "wm-actions/set-focus",
                    "data": {"id": view_id}
                }).encode("utf8")
                sock.client.send(len(msg).to_bytes(4, byteorder="little") + msg)
                sock.read_message()
                return True
    except Exception as e:
        log.warning("Could not focus screenshot-tool: %s", e)
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass

    return False
