"""Post-capture output handling.

Handles:
- Saving to disk (with format conversion)
- Copying to clipboard
- Desktop notifications
- Sound feedback
- JSON output for scripting
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

from .config import Config, get_config
from .emit import emit
from .hooks import notify_save

log = logging.getLogger(__name__)


@dataclass
class OutputOptions:
    """Options for output handling."""

    output_path: Optional[Path] = None  # Custom output path
    output_format: str = "png"  # png, jpg, webp
    quality: int = 90  # Quality for lossy formats

    clipboard: bool = True
    notification: bool = True
    sound: bool = True

    # Output modes (mutually exclusive)
    stdout: bool = False  # Print path to stdout
    json_output: bool = False  # Output JSON metadata

    # Silent mode - for scripting
    silent: bool = False  # Disables clipboard/notification/sound, uses tmp dir

    def __post_init__(self):
        if self.silent:
            self.clipboard = False
            self.notification = False
            self.sound = False


@dataclass
class OutputResult:
    """Result of saving a screenshot."""

    path: Path
    width: int
    height: int
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def _copy_to_clipboard(path: Path):
    """Copy image to clipboard using wl-copy."""
    try:
        with open(path, "rb") as f:
            subprocess.run(["wl-copy", "-t", "image/png"], stdin=f, check=True)
        log.debug("Copied to clipboard")
    except Exception as e:
        log.warning("Failed to copy to clipboard: %s", e)


def _play_sound():
    """Play camera shutter sound."""
    try:
        subprocess.Popen(
            ["canberra-gtk-play", "-i", "screen-capture"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        log.debug("Could not play sound: %s", e)


def _show_notification(path: Path, width: int, height: int):
    """Show desktop notification."""
    try:
        gi.require_version("Notify", "0.7")
        from gi.repository import Notify
        Notify.init("Screenshot Tool")
        notification = Notify.Notification.new(
            "Screenshot Captured",
            f"Saved to {path.name}\n{width}x{height} pixels",
            "camera-photo",
        )
        notification.set_urgency(Notify.Urgency.LOW)
        notification.show()
    except Exception as e:
        log.debug("Could not show notification: %s", e)


def save(
    source_path: Path,
    options: Optional[OutputOptions] = None,
    config: Optional[Config] = None,
) -> OutputResult:
    """Save screenshot with all post-processing.

    Args:
        source_path: Path to the captured image (will be deleted after processing)
        options: Output options
        config: Configuration object

    Returns:
        OutputResult with final path and metadata
    """
    options = options or OutputOptions()
    config = config or get_config()

    # Load image
    img = GdkPixbuf.Pixbuf.new_from_file(str(source_path))
    width = img.get_width()
    height = img.get_height()

    # Determine output path
    if options.output_path:
        output_path = options.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
    elif options.silent:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = config.silent_output_dir / f"screenshot_{timestamp}.{options.output_format}"
    else:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = config.output_dir / f"screenshot_{timestamp}.{options.output_format}"

    # Save in requested format
    output_format = options.output_format.lower()
    if output_format == "png":
        img.savev(str(output_path), "png", [], [])
    elif output_format in ("jpg", "jpeg"):
        img.savev(str(output_path), "jpeg", ["quality"], [str(options.quality)])
    elif output_format == "webp":
        try:
            img.savev(str(output_path), "webp", ["quality"], [str(options.quality)])
        except Exception:
            # Fallback to PNG if webp not supported
            output_path = output_path.with_suffix(".png")
            img.savev(str(output_path), "png", [], [])
    else:
        # Default to PNG for unknown formats
        img.savev(str(output_path), "png", [], [])

    # Post-processing
    if options.clipboard:
        _copy_to_clipboard(output_path)

    if options.sound:
        _play_sound()

    if options.notification:
        _show_notification(output_path, width, height)

    # Create result
    result = OutputResult(
        path=output_path,
        width=width,
        height=height,
        timestamp=datetime.now().isoformat(),
    )

    # Emit artifact.created event
    emit("artifact.created", {
        "file_path": str(output_path),
        "file_type": "screenshot",
        "metadata": {
            "width": width,
            "height": height,
            "format": options.output_format,
            "timestamp": result.timestamp,
        },
    })

    # Notify hooks (runs asynchronously, won't block)
    notify_save(result, config)

    # Output modes
    if options.json_output:
        print(result.to_json(), flush=True)
    elif options.stdout:
        print(str(output_path), flush=True)
    else:
        log.info("Screenshot saved: %s", output_path)

    return result


def save_pixbuf(
    pixbuf: GdkPixbuf.Pixbuf,
    options: Optional[OutputOptions] = None,
    config: Optional[Config] = None,
) -> OutputResult:
    """Save a GdkPixbuf directly (for UI cropped regions).

    Args:
        pixbuf: The image to save
        options: Output options
        config: Configuration object

    Returns:
        OutputResult with final path and metadata
    """
    import tempfile

    # Save to temp file first
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        temp_path = Path(tmp.name)
    pixbuf.savev(str(temp_path), "png", [], [])

    # Use main save function
    result = save(temp_path, options, config)

    # Clean up temp file
    temp_path.unlink(missing_ok=True)

    return result
