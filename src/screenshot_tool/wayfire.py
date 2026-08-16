"""Optional Wayfire IPC integration.

All functions gracefully degrade if Wayfire is not available.
This module handles:
- Window geometry retrieval (for window selection)
- Cursor position (for initial magnifier placement)
"""

import logging

log = logging.getLogger(__name__)


def _get_socket():
    """Get a Wayfire IPC socket, or None if unavailable."""
    try:
        from wayfire import WayfireSocket

        sock = WayfireSocket()
        sock.client.settimeout(1.0)
        return sock
    except Exception as e:  # noqa: BLE001 - optional third-party IPC must degrade safely.
        log.debug("Wayfire IPC unavailable: %s", e)
        return None


def get_cursor_position() -> tuple[int, int] | None:
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
    except Exception as e:  # noqa: BLE001 - optional third-party IPC must degrade safely.
        log.debug("Could not get cursor position: %s", e)
        return None
    finally:
        try:
            sock.close()
        except Exception as exc:  # noqa: BLE001 - best-effort third-party cleanup.
            log.debug("Could not close Wayfire IPC socket: %s", exc)


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
        identifiers: dict[int, str] = {}
        try:
            response = sock.send_json(
                {"method": "ext-toplevel/list-identifiers", "data": {}}
            )
            identifiers = {
                int(item["view-id"]): str(item["identifier"])
                for item in response.get("identifiers", [])
                if item.get("view-id") is not None and item.get("identifier")
            }
        except Exception as exc:  # noqa: BLE001 - old compositor degrades closed.
            log.debug("Could not get exact capture identifiers: %s", exc)

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
                    windows.append(
                        {
                            "id": view.get("id"),
                            "capture_identifier": identifiers.get(view.get("id"), ""),
                            "title": view.get("title", "Unknown"),
                            "app_id": app_id,
                            "x": geo.get("x", 0),
                            "y": geo.get("y", 0),
                            "width": geo.get("width", 0),
                            "height": geo.get("height", 0),
                            "focus_timestamp": view.get("last-focus-timestamp", 0),
                        }
                    )

        # Sort by focus timestamp descending (most recently focused = front)
        windows.sort(key=lambda w: w["focus_timestamp"], reverse=True)

        # Assign z_order after sorting
        for i, window in enumerate(windows):
            window["z_order"] = i

    except Exception as e:  # noqa: BLE001 - optional third-party IPC must degrade safely.
        log.warning("Could not get window geometries: %s", e)

    finally:
        try:
            sock.close()
        except Exception as exc:  # noqa: BLE001 - best-effort third-party cleanup.
            log.debug("Could not close Wayfire IPC socket: %s", exc)

    return windows
