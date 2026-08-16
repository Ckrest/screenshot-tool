"""Join Wayfire window geometry to standard capture sources by opaque ID."""

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .config import Config, load_config
from .wayfire import get_window_geometries

if TYPE_CHECKING:
    from .models import RawFrame

log = logging.getLogger(__name__)

@dataclass(frozen=True)
class Window:
    """Unified window representation used throughout the screenshot tool."""

    app_id: str
    capture_id: str
    title: str
    view_id: int | None
    x: int
    y: int
    width: int
    height: int
    z_order: int = 0

    @property
    def geometry(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    def mapped_to_frame(self, frame: RawFrame) -> Window:
        from .models import Rect

        geometry = frame.logical_rect_to_frame(
            Rect(self.x, self.y, self.width, self.height)
        )
        return Window(
            self.app_id,
            self.capture_id,
            self.title,
            self.view_id,
            geometry.x,
            geometry.y,
            geometry.width,
            geometry.height,
            self.z_order,
        )


def _normalize(value: str) -> str:
    return value.strip().lower()


def _list_capture_windows(config: Config) -> list[dict]:
    """Fetch window list from wayland-capture.

    Only sources with the standard opaque identifier are returned.
    """
    try:
        result = subprocess.run(
            [config.wayland_capture, "--list", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            log.warning("wayland-capture --list failed: %s", result.stderr)
            return []

        data = json.loads(result.stdout)
        windows = []
        for window in data.get("windows", []):
            capture_id = str(window.get("identifier", ""))
            if not capture_id:
                continue
            windows.append(
                {
                    "capture_id": capture_id,
                    "app_id": window.get("app_id", ""),
                    "title": window.get("title", ""),
                }
            )
        return windows
    except (
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        AttributeError,
    ) as e:
        log.warning("Could not list capture windows: %s", e)
        return []


def enumerate_windows(config: Config | None = None) -> list[Window]:
    """Return windows joined exclusively by the standard opaque identifier.

    A Wayfire window without an identifier, or whose identifier is absent from
    the capture protocol list, remains visible for highlighting but is marked
    uncapturable. App IDs and titles are never identity fallbacks.
    """
    config = config or load_config()

    wayfire_windows = get_window_geometries()
    capture_windows = _list_capture_windows(config)

    capture_by_identifier = {
        item["capture_id"]: item for item in capture_windows
    }
    paired: list[Window] = []

    for wf in wayfire_windows:
        identifier = str(wf.get("capture_identifier", ""))
        match = capture_by_identifier.get(identifier) if identifier else None

        paired.append(
            Window(
                app_id=wf.get("app_id", ""),
                capture_id=identifier if match else "",
                title=match["title"] if match else wf.get("title", ""),
                view_id=wf.get("id"),
                x=wf.get("x", 0),
                y=wf.get("y", 0),
                width=wf.get("width", 0),
                height=wf.get("height", 0),
                z_order=wf.get("z_order", 0),
            )
        )

    return paired


def find_window_by_app_id(app_id: str, config: Config | None = None) -> Window | None:
    """Find the frontmost window matching the given canonical app-id."""
    normalized = _normalize(app_id)
    windows = enumerate_windows(config)

    matches = [
        w for w in windows if _normalize(w.app_id) == normalized and w.capture_id
    ]
    if not matches:
        return None

    # Prefer the frontmost window (lowest z_order).
    matches.sort(key=lambda w: w.z_order)
    return matches[0]


def find_window_at(x: float, y: float, config: Config | None = None) -> Window | None:
    """Find the topmost window containing the given coordinates."""
    return find_window_in_list(enumerate_windows(config), x, y)


def find_window_in_list(windows: list[Window], x: float, y: float) -> Window | None:
    """Find the topmost window containing the given coordinates in a snapshot."""
    windows = sorted(windows, key=lambda w: w.z_order)
    for window in windows:
        wx, wy = window.x, window.y
        ww, wh = window.width, window.height
        if wx <= x < wx + ww and wy <= y < wy + wh:
            return window
    return None
