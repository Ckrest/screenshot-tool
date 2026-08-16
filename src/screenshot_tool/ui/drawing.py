"""GTK4 selection overlay rendering."""

from __future__ import annotations

import math

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk

from ..models import CoordinateMapper, Rect, SelectionModel
from ..window import Window, find_window_in_list

MAGNIFIER_DIAMETER = 480
MAGNIFIER_ZOOM = 8
MAGNIFIER_GAP = 32
MAGNIFIER_MARGIN = 12


def magnifier_geometry(
    cursor_x: float,
    cursor_y: float,
    width: int,
    height: int,
    diameter: int = MAGNIFIER_DIAMETER,
) -> tuple[float, float, float]:
    """Place the magnifier diagonally from the cursor within the canvas."""
    size = max(
        0,
        min(
            diameter,
            width - 2 * MAGNIFIER_MARGIN,
            height - 2 * MAGNIFIER_MARGIN,
        ),
    )
    x = (
        cursor_x + MAGNIFIER_GAP
        if cursor_x + MAGNIFIER_GAP + size <= width - MAGNIFIER_MARGIN
        else cursor_x - MAGNIFIER_GAP - size
    )
    y = (
        cursor_y + MAGNIFIER_GAP
        if cursor_y + MAGNIFIER_GAP + size <= height - MAGNIFIER_MARGIN
        else cursor_y - MAGNIFIER_GAP - size
    )
    x = min(
        max(MAGNIFIER_MARGIN, x),
        max(MAGNIFIER_MARGIN, width - size - MAGNIFIER_MARGIN),
    )
    y = min(
        max(MAGNIFIER_MARGIN, y),
        max(MAGNIFIER_MARGIN, height - size - MAGNIFIER_MARGIN),
    )
    return x, y, float(size)


class OverlayDrawing:
    def __init__(
        self,
        model: SelectionModel,
        mapper: CoordinateMapper,
        pixbuf,
        windows: list[Window],
    ) -> None:
        self.model, self.mapper, self.pixbuf, self.windows = (
            model,
            mapper,
            pixbuf,
            windows,
        )

    def hovered_window(self) -> Window | None:
        return find_window_in_list(
            self.windows, self.model.cursor_x, self.model.cursor_y
        )

    def draw(self, area, cr, width: int, height: int) -> None:
        selection = self.model.selection
        hovered = self.hovered_window() if selection is None else None
        highlighted = selection or (
            Rect(hovered.x, hovered.y, hovered.width, hovered.height)
            if hovered
            else None
        )

        cr.set_source_rgba(0, 0, 0, 0.26)
        cr.paint()
        if highlighted:
            x, y = self.mapper.frame_to_widget(
                highlighted.x, highlighted.y, width, height
            )
            right, bottom = self.mapper.frame_to_widget(
                highlighted.x + highlighted.width,
                highlighted.y + highlighted.height,
                width,
                height,
            )
            cr.save()
            cr.set_operator(1)  # SOURCE
            cr.set_source_rgba(0, 0, 0, 0)
            cr.rectangle(x, y, right - x, bottom - y)
            cr.fill()
            cr.restore()
            cr.set_source_rgba(0.18, 0.68, 1.0, 0.95)
            cr.set_line_width(2)
            cr.rectangle(x + 1, y + 1, max(0, right - x - 2), max(0, bottom - y - 2))
            cr.stroke()
            self._dimensions(cr, highlighted, x, y, right, bottom, width, height)

        if self.mapper.contains_frame(self.model.cursor_x, self.model.cursor_y):
            cursor_x, cursor_y = self.mapper.frame_to_widget(
                self.model.cursor_x,
                self.model.cursor_y,
                width,
                height,
            )
            cr.set_source_rgba(1, 1, 1, 0.85)
            cr.set_line_width(1)
            cr.move_to(0, cursor_y + 0.5)
            cr.line_to(width, cursor_y + 0.5)
            cr.move_to(cursor_x + 0.5, 0)
            cr.line_to(cursor_x + 0.5, height)
            cr.stroke()
            self._magnifier(cr, cursor_x, cursor_y, width, height)

    def _dimensions(
        self,
        cr,
        rect: Rect,
        x: float,
        y: float,
        right: float,
        bottom: float,
        width: int,
        height: int,
    ) -> None:
        text = f"{rect.width} × {rect.height}"
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(13)
        extents = cr.text_extents(text)
        box_width = extents.width + 16
        box_height = 26
        box_x = min(max(8, x), max(8, width - box_width - 8))
        box_y = (
            bottom + 8
            if bottom + box_height + 8 < height
            else max(8, y - box_height - 8)
        )
        cr.set_source_rgba(0.06, 0.08, 0.11, 0.92)
        cr.rectangle(box_x, box_y, box_width, box_height)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 1)
        cr.move_to(box_x + 8, box_y + 18)
        cr.show_text(text)

    def _magnifier(
        self, cr, cursor_x: float, cursor_y: float, width: int, height: int
    ) -> None:
        x, y, size = magnifier_geometry(cursor_x, cursor_y, width, height)
        if size < 4:
            return
        center_x, center_y = x + size / 2, y + size / 2
        radius = size / 2
        cr.save()
        cr.arc(center_x, center_y, radius, 0, math.tau)
        cr.clip()
        cr.translate(center_x, center_y)
        cr.scale(MAGNIFIER_ZOOM, MAGNIFIER_ZOOM)
        Gdk.cairo_set_source_pixbuf(
            cr, self.pixbuf, -self.model.cursor_x, -self.model.cursor_y
        )
        cr.get_source().set_filter(3)  # NEAREST
        cr.paint()
        cr.restore()
        cr.set_source_rgba(0.05, 0.07, 0.1, 0.95)
        cr.set_line_width(5)
        cr.arc(center_x, center_y, radius - 2.5, 0, math.tau)
        cr.stroke()
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.set_line_width(1)
        cr.arc(center_x, center_y, radius - 5.5, 0, math.tau)
        cr.stroke()
        crosshair_radius = radius - 7
        cr.move_to(center_x, center_y - crosshair_radius)
        cr.line_to(center_x, center_y + crosshair_radius)
        cr.move_to(center_x - crosshair_radius, center_y)
        cr.line_to(center_x + crosshair_radius, center_y)
        cr.stroke()
