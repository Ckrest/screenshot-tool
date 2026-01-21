"""Core screenshot capture functions.

Uses wayland-capture binary for the actual screen capture.
All functions return a temporary file path that must be handled by the caller.
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .config import Config, get_config

log = logging.getLogger(__name__)


class CaptureError(Exception):
    """Raised when capture fails."""
    pass


def get_primary_output(config: Optional[Config] = None) -> Optional[str]:
    """Get the primary output name from wayland-capture.

    Returns:
        Output name (e.g., 'eDP-1') or None if unavailable
    """
    config = config or get_config()
    try:
        result = subprocess.run(
            [config.wayland_capture, "--list", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            outputs = data.get("outputs", [])
            if outputs:
                return outputs[0].get("name")
    except Exception as e:
        log.warning("Could not get output list: %s", e)
    return None


def list_outputs(config: Optional[Config] = None) -> list[dict]:
    """List all available outputs.

    Returns:
        List of output dicts with keys: name, description, width, height, x, y
    """
    config = config or get_config()
    try:
        result = subprocess.run(
            [config.wayland_capture, "--list", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("outputs", [])
    except Exception as e:
        log.warning("Could not list outputs: %s", e)
    return []


def list_windows(config: Optional[Config] = None) -> list[dict]:
    """List all available windows.

    Returns:
        List of window dicts with keys: app_id, title
    """
    config = config or get_config()
    try:
        result = subprocess.run(
            [config.wayland_capture, "--list", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("windows", [])
    except Exception as e:
        log.warning("Could not list windows: %s", e)
    return []


def fullscreen(
    monitor: Optional[str] = None,
    config: Optional[Config] = None,
) -> Path:
    """Capture full screen (or specific monitor).

    Args:
        monitor: Output name (e.g., 'eDP-1'). If None, uses primary.
        config: Configuration object. If None, uses global config.

    Returns:
        Path to temporary PNG file

    Raises:
        CaptureError: If capture fails
    """
    config = config or get_config()

    # Create temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp_path = Path(tmp.name)
    tmp.close()

    # Get output name if not specified
    output_name = monitor or get_primary_output(config)
    if not output_name:
        raise CaptureError("Could not determine output to capture")

    try:
        result = subprocess.run(
            [config.wayland_capture, "--output", output_name, "--output-file", str(temp_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            temp_path.unlink(missing_ok=True)
            raise CaptureError(f"Screen capture failed: {result.stderr}")

        return temp_path

    except subprocess.TimeoutExpired:
        temp_path.unlink(missing_ok=True)
        raise CaptureError("Screen capture timed out")
    except FileNotFoundError:
        temp_path.unlink(missing_ok=True)
        raise CaptureError(f"wayland-capture not found: {config.wayland_capture}")


def region(
    x: int,
    y: int,
    width: int,
    height: int,
    config: Optional[Config] = None,
) -> Path:
    """Capture a specific region of the screen.

    Args:
        x: X coordinate of top-left corner
        y: Y coordinate of top-left corner
        width: Width of region
        height: Height of region
        config: Configuration object. If None, uses global config.

    Returns:
        Path to temporary PNG file

    Raises:
        CaptureError: If capture fails
    """
    config = config or get_config()

    # Create temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp_path = Path(tmp.name)
    tmp.close()

    # Get primary output for region capture
    output_name = get_primary_output(config)
    if not output_name:
        raise CaptureError("Could not determine output to capture")

    try:
        result = subprocess.run(
            [
                config.wayland_capture,
                "--output", output_name,
                "--region", f"{x},{y},{width},{height}",
                "--output-file", str(temp_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            temp_path.unlink(missing_ok=True)
            raise CaptureError(f"Region capture failed: {result.stderr}")

        return temp_path

    except subprocess.TimeoutExpired:
        temp_path.unlink(missing_ok=True)
        raise CaptureError("Region capture timed out")


def window(
    app_id: str,
    config: Optional[Config] = None,
) -> Path:
    """Capture a specific window by app-id.

    Args:
        app_id: The Wayland app-id (e.g., 'kitty', 'brave-browser')
        config: Configuration object. If None, uses global config.

    Returns:
        Path to temporary PNG file

    Raises:
        CaptureError: If capture fails
    """
    config = config or get_config()

    # Create temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp_path = Path(tmp.name)
    tmp.close()

    try:
        result = subprocess.run(
            [config.wayland_capture, "--window", app_id, "--output-file", str(temp_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            temp_path.unlink(missing_ok=True)
            raise CaptureError(f"Window capture failed: {result.stderr}")

        return temp_path

    except subprocess.TimeoutExpired:
        temp_path.unlink(missing_ok=True)
        raise CaptureError("Window capture timed out")
