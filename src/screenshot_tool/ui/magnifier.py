"""Magnifier component for pixel-perfect positioning."""

import math

import cairo
import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk


class Magnifier:
    """Magnifier circle showing zoomed pixels under cursor."""

    def __init__(self, radius: int = 225, zoom: int = 50):
        """Initialize magnifier.

        Args:
            radius: Radius of the magnifier circle
            zoom: Pixel size in the magnified view
        """
        self.radius = radius
        self.zoom = zoom
        self.pixels_shown = 9  # 9x9 grid

    def draw(
        self,
        cr: cairo.Context,
        cursor_x: float,
        cursor_y: float,
        screenshot,
        img_width: int,
        img_height: int,
    ):
        """Draw the magnifier at the appropriate position.

        Args:
            cr: Cairo context
            cursor_x: Current cursor X position
            cursor_y: Current cursor Y position
            screenshot: GdkPixbuf screenshot
            img_width: Screenshot width
            img_height: Screenshot height
        """
        diameter = self.radius * 2

        # Position magnifier to avoid cursor
        mag_x = cursor_x + 40
        mag_y = cursor_y - 40 - diameter

        # Adjust if would go off screen
        if mag_x + diameter > img_width:
            mag_x = cursor_x - 40 - diameter
        if mag_x < 0:
            mag_x = 40
        if mag_y < 0:
            mag_y = cursor_y + 40
        if mag_y + diameter > img_height:
            mag_y = img_height - diameter - 40

        center_x = mag_x + self.radius
        center_y = mag_y + self.radius

        # White border
        cr.save()
        cr.arc(center_x, center_y, self.radius + 2, 0, 2 * math.pi)
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(3)
        cr.stroke()
        cr.restore()

        # Clip to circle for content
        cr.save()
        cr.arc(center_x, center_y, self.radius, 0, 2 * math.pi)
        cr.clip()

        # Draw magnified content
        center_pixel_x = int(cursor_x)
        center_pixel_y = int(cursor_y)
        src_x = max(0, center_pixel_x - 4)
        src_y = max(0, center_pixel_y - 4)
        draw_x = center_x - (self.pixels_shown * self.zoom) / 2
        draw_y = center_y - (self.pixels_shown * self.zoom) / 2

        cr.save()
        cr.translate(draw_x, draw_y)
        cr.scale(self.zoom, self.zoom)
        cr.translate(-src_x, -src_y)
        Gdk.cairo_set_source_pixbuf(cr, screenshot, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()

        # Grid lines
        cr.save()
        cr.arc(center_x, center_y, self.radius, 0, 2 * math.pi)
        cr.clip()

        grid_start_x = center_x - (self.pixels_shown * self.zoom) / 2
        grid_start_y = center_y - (self.pixels_shown * self.zoom) / 2

        cr.set_source_rgba(0.3, 0.3, 0.3, 0.6)
        cr.set_line_width(1)

        for i in range(self.pixels_shown + 1):
            line_x = grid_start_x + i * self.zoom
            cr.move_to(line_x, grid_start_y)
            cr.line_to(line_x, grid_start_y + self.pixels_shown * self.zoom)
        for i in range(self.pixels_shown + 1):
            line_y = grid_start_y + i * self.zoom
            cr.move_to(grid_start_x, line_y)
            cr.line_to(grid_start_x + self.pixels_shown * self.zoom, line_y)
        cr.stroke()
        cr.restore()

        # Center pixel highlight
        cr.save()
        cr.set_source_rgb(1, 0.2, 0.2)
        cr.set_line_width(3)
        box_x = center_x - self.zoom / 2
        box_y = center_y - self.zoom / 2
        cr.rectangle(box_x, box_y, self.zoom, self.zoom)
        cr.stroke()
        cr.restore()

        cr.restore()

        # Coordinates label
        self._draw_coordinates(cr, center_x, mag_y + diameter, cursor_x, cursor_y)

    def _draw_coordinates(
        self,
        cr: cairo.Context,
        center_x: float,
        bottom_y: float,
        cursor_x: float,
        cursor_y: float,
    ):
        """Draw coordinates below the magnifier."""
        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(12)
        coord_text = f"({int(cursor_x)}, {int(cursor_y)})"
        extents = cr.text_extents(coord_text)

        text_x = center_x - extents.width / 2
        text_y = bottom_y + 15

        # Background
        cr.set_source_rgba(0, 0, 0, 0.7)
        cr.rectangle(
            text_x - 5,
            text_y - extents.height - 2,
            extents.width + 10,
            extents.height + 6,
        )
        cr.fill()

        # Text
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(text_x, text_y)
        cr.show_text(coord_text)
