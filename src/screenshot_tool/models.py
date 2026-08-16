"""Pure contracts shared by the service, capture adapter, UI, and output pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def normalized(self) -> Rect:
        x, width = (
            (self.x, self.width)
            if self.width >= 0
            else (self.x + self.width, -self.width)
        )
        y, height = (
            (self.y, self.height)
            if self.height >= 0
            else (self.y + self.height, -self.height)
        )
        return Rect(x, y, width, height)

    def clamp(self, width: int, height: int) -> Rect:
        value = self.normalized()
        x = max(0, min(value.x, width))
        y = max(0, min(value.y, height))
        right = max(x, min(value.x + value.width, width))
        bottom = max(y, min(value.y + value.height, height))
        return Rect(x, y, right - x, bottom - y)


@dataclass(frozen=True)
class OutputLayout:
    """One output's logical placement and viewport in a composite frame."""

    name: str
    logical_x: int
    logical_y: int
    logical_width: int
    logical_height: int
    buffer_width: int
    buffer_height: int
    scale: float
    transform: str
    frame_x: int
    frame_y: int
    frame_width: int
    frame_height: int

    @property
    def frame_rect(self) -> Rect:
        return Rect(self.frame_x, self.frame_y, self.frame_width, self.frame_height)


@dataclass(frozen=True)
class RawFrame:
    width: int
    height: int
    stride: int
    pixels: bytes
    pixel_format: str = "rgba8888"
    alpha: str = "straight"
    transform: str = "normal"
    output_name: str | None = None
    logical_origin: tuple[int, int] = (0, 0)
    canvas_scale: float = 1.0
    outputs: tuple[OutputLayout, ...] = ()

    def crop(self, rect: Rect) -> RawFrame:
        area = rect.clamp(self.width, self.height)
        if area.width < 1 or area.height < 1:
            raise ValueError("Capture region is empty")
        row_bytes = area.width * 4
        data = bytearray(row_bytes * area.height)
        for row in range(area.height):
            source = (area.y + row) * self.stride + area.x * 4
            target = row * row_bytes
            data[target : target + row_bytes] = self.pixels[source : source + row_bytes]
        return RawFrame(
            area.width,
            area.height,
            row_bytes,
            bytes(data),
            self.pixel_format,
            self.alpha,
        )

    def logical_point_to_frame(self, x: float, y: float) -> tuple[int, int]:
        origin_x, origin_y = self.logical_origin
        return (
            round((x - origin_x) * self.canvas_scale),
            round((y - origin_y) * self.canvas_scale),
        )

    def logical_rect_to_frame(self, rect: Rect) -> Rect:
        area = rect.normalized()
        x, y = self.logical_point_to_frame(area.x, area.y)
        right, bottom = self.logical_point_to_frame(
            area.x + area.width, area.y + area.height
        )
        return Rect(x, y, right - x, bottom - y).clamp(self.width, self.height)

    def output(self, name: str) -> OutputLayout | None:
        return next((item for item in self.outputs if item.name == name), None)


@dataclass(frozen=True)
class CaptureRequest:
    mode: str = "interactive"
    request_id: str = field(default_factory=lambda: str(uuid4()))
    region: Rect | None = None
    window_app_id: str | None = None
    monitor: str | None = None
    config_path: Path | None = None
    output_path: Path | None = None
    output_format: str | None = None
    quality: int | None = None
    clipboard: bool | None = None
    notification: bool | None = None
    sound: bool | None = None
    silent: bool = False
    delay_ms: int = 0

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> CaptureRequest:
        mode = str(values.get("mode", "interactive"))
        region = values.get("region")
        parsed_region = None
        if region:
            parts = [int(part) for part in str(region).split(",")]
            if len(parts) != 4:
                raise ValueError("region must be X,Y,W,H")
            parsed_region = Rect(*parts)
        return cls(
            mode=mode,
            request_id=str(values.get("request_id") or uuid4()),
            region=parsed_region,
            window_app_id=values.get("window"),
            monitor=values.get("monitor"),
            config_path=Path(values["config_path"]).expanduser()
            if values.get("config_path")
            else None,
            output_path=Path(values["output"]).expanduser()
            if values.get("output")
            else None,
            output_format=values.get("format"),
            quality=int(values["quality"])
            if values.get("quality") is not None
            else None,
            clipboard=values.get("clipboard"),
            notification=values.get("notification"),
            sound=values.get("sound"),
            silent=bool(values.get("silent", False)),
            delay_ms=max(0, int(values.get("delay_ms", 0))),
        )


@dataclass(frozen=True)
class OutputOptions:
    output_path: Path | None
    output_format: str
    quality: int
    clipboard: bool
    notification: bool
    sound: bool
    silent: bool = False


@dataclass(frozen=True)
class OutputResult:
    path: Path
    width: int
    height: int
    timestamp: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "timestamp": self.timestamp,
            "source": self.source,
        }


class CoordinateMapper:
    """Maps frozen-frame pixels to a possibly scaled GTK allocation."""

    def __init__(
        self, frame_width: int, frame_height: int, viewport: Rect | None = None
    ) -> None:
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.viewport = viewport or Rect(0, 0, frame_width, frame_height)

    def widget_to_frame(
        self, x: float, y: float, width: int, height: int
    ) -> tuple[int, int]:
        return (
            max(
                self.viewport.x,
                min(
                    self.viewport.x + self.viewport.width - 1,
                    self.viewport.x
                    + round(x * self.viewport.width / max(1, width)),
                ),
            ),
            max(
                self.viewport.y,
                min(
                    self.viewport.y + self.viewport.height - 1,
                    self.viewport.y
                    + round(y * self.viewport.height / max(1, height)),
                ),
            ),
        )

    def frame_to_widget(
        self, x: float, y: float, width: int, height: int
    ) -> tuple[float, float]:
        return (
            (x - self.viewport.x) * width / self.viewport.width,
            (y - self.viewport.y) * height / self.viewport.height,
        )

    def contains_frame(self, x: float, y: float) -> bool:
        return (
            self.viewport.x <= x < self.viewport.x + self.viewport.width
            and self.viewport.y <= y < self.viewport.y + self.viewport.height
        )


class SelectionModel:
    def __init__(
        self, width: int, height: int, cursor: tuple[int, int] = (0, 0)
    ) -> None:
        self.width, self.height = width, height
        self.cursor_x = max(0, min(width - 1, cursor[0]))
        self.cursor_y = max(0, min(height - 1, cursor[1]))
        self.anchor: tuple[int, int] | None = None

    def move(self, x: int, y: int) -> None:
        self.cursor_x = max(0, min(self.width - 1, x))
        self.cursor_y = max(0, min(self.height - 1, y))

    def nudge(self, dx: int, dy: int) -> None:
        self.move(self.cursor_x + dx, self.cursor_y + dy)

    def begin(self) -> None:
        self.anchor = (self.cursor_x, self.cursor_y)

    def clear(self) -> None:
        self.anchor = None

    @property
    def selection(self) -> Rect | None:
        if self.anchor is None:
            return None
        x, y = self.anchor
        return Rect(x, y, self.cursor_x - x, self.cursor_y - y).normalized()
