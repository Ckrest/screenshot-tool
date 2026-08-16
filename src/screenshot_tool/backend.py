"""Strict adapter for wayland-capture's raw-frame contract."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from .config import Config, runtime_dir
from .models import OutputLayout, RawFrame


class CaptureError(RuntimeError):
    pass


class WaylandCaptureBackend:
    SCHEMA = "wayland-capture/frame@1"

    def __init__(self, config: Config) -> None:
        self.binary = config.wayland_capture

    def capture_desktop(
        self, monitor: str | None = None, delay_ms: int = 0
    ) -> RawFrame:
        source = ["--output", monitor] if monitor else ["--all-outputs"]
        return self._capture(source, delay_ms)

    def capture_window(self, capture_id: str, delay_ms: int = 0) -> RawFrame:
        if not capture_id:
            raise CaptureError("The selected window has no capture identifier")
        return self._capture(["--window-id", capture_id], delay_ms)

    def _capture(self, source_args: list[str], delay_ms: int) -> RawFrame:
        root = runtime_dir()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        descriptor, filename = tempfile.mkstemp(
            prefix="frame-", suffix=".rgba", dir=root
        )
        os.close(descriptor)
        path = Path(filename)
        command = [
            self.binary,
            *source_args,
            "--format",
            "raw",
            "--output-file",
            str(path),
            "--json",
        ]
        if delay_ms:
            command.extend(["--delay", str(delay_ms)])
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=30, check=False
            )
            if completed.returncode:
                detail = (
                    completed.stderr.strip()
                    or completed.stdout.strip()
                    or "unknown capture error"
                )
                raise CaptureError(detail)
            try:
                metadata = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise CaptureError("wayland-capture returned invalid JSON") from exc
            return self._load_frame(path, metadata)
        except subprocess.TimeoutExpired as exc:
            raise CaptureError("wayland-capture timed out") from exc
        except OSError as exc:
            raise CaptureError(f"Could not run {self.binary}: {exc}") from exc
        finally:
            path.unlink(missing_ok=True)

    @classmethod
    def _load_frame(cls, path: Path, metadata: dict) -> RawFrame:
        if metadata.get("schema") != cls.SCHEMA or metadata.get("type") != "raw":
            raise CaptureError("Unsupported wayland-capture frame schema")
        if (
            metadata.get("pixel_format") != "rgba8888"
            or metadata.get("alpha") != "straight"
        ):
            raise CaptureError(
                "Screenshot Tool requires straight-alpha rgba8888 frames"
            )
        if metadata.get("transform", "normal") != "normal":
            raise CaptureError("Transformed raw outputs are not yet supported")
        if metadata.get("cursor_included") is not False:
            raise CaptureError("The capture backend unexpectedly included the cursor")
        try:
            width = int(metadata["width"])
            height = int(metadata["height"])
            stride = int(metadata["stride"])
            pixels = path.read_bytes()
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise CaptureError("Incomplete raw-frame metadata") from exc
        if (
            width < 1
            or height < 1
            or stride < width * 4
            or len(pixels) != stride * height
        ):
            raise CaptureError("Raw-frame dimensions do not match its pixel payload")
        source = metadata.get("source", {})
        try:
            origin = source.get("logical_origin", {"x": 0, "y": 0})
            canvas_scale = float(source.get("canvas_scale", 1.0))
            outputs = tuple(
                OutputLayout(
                    name=str(item["name"]),
                    logical_x=int(item["logical_x"]),
                    logical_y=int(item["logical_y"]),
                    logical_width=int(item["logical_width"]),
                    logical_height=int(item["logical_height"]),
                    buffer_width=int(item["buffer_width"]),
                    buffer_height=int(item["buffer_height"]),
                    scale=float(item["scale"]),
                    transform=str(item["transform"]),
                    frame_x=int(item["frame_x"]),
                    frame_y=int(item["frame_y"]),
                    frame_width=int(item["frame_width"]),
                    frame_height=int(item["frame_height"]),
                )
                for item in source.get("outputs", [])
            )
            logical_origin = (int(origin["x"]), int(origin["y"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise CaptureError("Invalid output-layout metadata") from exc
        if canvas_scale <= 0:
            raise CaptureError("Invalid output-layout canvas scale")
        for output in outputs:
            area = output.frame_rect
            if (
                output.logical_width < 1
                or output.logical_height < 1
                or output.buffer_width < 1
                or output.buffer_height < 1
                or output.scale <= 0
                or area.width < 1
                or area.height < 1
                or area.x < 0
                or area.y < 0
                or area.x + area.width > width
                or area.y + area.height > height
            ):
                raise CaptureError("Invalid output-layout geometry")
        if source.get("type") in {"desktop", "output"} and not outputs:
            raise CaptureError("Capture backend omitted output-layout metadata")
        return RawFrame(
            width,
            height,
            stride,
            pixels,
            output_name=source.get("name"),
            logical_origin=logical_origin,
            canvas_scale=canvas_scale,
            outputs=outputs,
        )
