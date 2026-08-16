"""Single-encode, atomic screenshot output pipeline."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib

from .config import Config
from .models import CaptureRequest, OutputOptions, OutputResult, RawFrame

log = logging.getLogger(__name__)

MIME_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def options_for_request(request: CaptureRequest, config: Config) -> OutputOptions:
    silent = request.silent
    path_format = (
        request.output_path.suffix.lstrip(".").lower() if request.output_path else ""
    )
    selected_format = (
        request.output_format
        or (path_format if path_format in MIME_TYPES else None)
        or config.default_format
    )
    return OutputOptions(
        output_path=request.output_path,
        output_format=selected_format.lower(),
        quality=request.quality
        if request.quality is not None
        else config.default_quality,
        clipboard=False
        if silent
        else (
            config.enable_clipboard if request.clipboard is None else request.clipboard
        ),
        notification=False
        if silent
        else (
            config.enable_notification
            if request.notification is None
            else request.notification
        ),
        sound=False
        if silent
        else (config.enable_sound if request.sound is None else request.sound),
        silent=silent,
    )


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned[:80] or "Window"


def app_display_name(app_id: str) -> str:
    """Resolve an app-id through desktop entries, with a stable raw-id fallback."""
    target = app_id.lower()
    for info in Gio.AppInfo.get_all():
        desktop_id = (info.get_id() or "").removesuffix(".desktop").lower()
        if target in {desktop_id, desktop_id.split(".")[-1]}:
            return _safe_component(info.get_display_name() or app_id)
    return _safe_component(app_id)


def _context_name(
    source: str, app_id: str | None, title: str | None, include_title: bool
) -> str:
    if source == "fullscreen":
        return "Fullscreen"
    if source == "region":
        return "Region"
    name = app_display_name(app_id or "Window")
    if include_title and title:
        name = f"{name}_{_safe_component(title)}"
    return name


def output_path(
    options: OutputOptions,
    config: Config,
    source: str,
    app_id: str | None = None,
    title: str | None = None,
    now: datetime | None = None,
) -> Path:
    if options.output_path:
        return options.output_path.expanduser()
    directory = config.silent_output_dir if options.silent else config.output_dir
    extension = "jpg" if options.output_format == "jpeg" else options.output_format
    current = now or datetime.now().astimezone()
    timestamp = current.strftime("%Y-%m-%d_%H-%M-%S")
    context = _context_name(source, app_id, title, config.include_window_title)
    base = directory / f"Screenshot_{timestamp}_{context}.{extension}"
    if not base.exists():
        return base
    for index in range(2, 1000):
        candidate = base.with_name(f"{base.stem}_{index}{base.suffix}")
        if not candidate.exists():
            return candidate
    return base.with_name(f"{base.stem}_{current.strftime('%f')}{base.suffix}")


def save_frame(
    frame: RawFrame,
    options: OutputOptions,
    config: Config,
    source: str,
    app_id: str | None = None,
    title: str | None = None,
) -> OutputResult:
    if options.output_format not in MIME_TYPES:
        raise ValueError(f"Unsupported output format: {options.output_format}")
    if not 1 <= options.quality <= 100:
        raise ValueError("Quality must be between 1 and 100")
    destination = output_path(options, config, source, app_id, title)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(frame.pixels),
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        frame.width,
        frame.height,
        frame.stride,
    )
    encoder = (
        "jpeg" if options.output_format in {"jpg", "jpeg"} else options.output_format
    )
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
    keys, values = (
        (["quality"], [str(options.quality)])
        if encoder in {"jpeg", "webp"}
        else ([], [])
    )
    try:
        pixbuf.savev(str(temporary), encoder, keys, values)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    timestamp = datetime.now().astimezone().isoformat()
    return OutputResult(destination, frame.width, frame.height, timestamp, source)


def copy_to_clipboard(path: Path, output_format: str) -> None:
    mime = MIME_TYPES[output_format]
    try:
        with path.open("rb") as stream:
            subprocess.run(
                ["wl-copy", "--type", mime],
                stdin=stream,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Could not copy screenshot to clipboard: %s", exc)
