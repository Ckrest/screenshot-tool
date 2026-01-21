"""Cairo drawing helpers for the screenshot overlay."""

import cairo


def draw_crosshair(cr: cairo.Context, x: float, y: float, size: int = 15):
    """Draw a crosshair cursor at the given position."""
    # Black outline
    cr.set_source_rgb(0, 0, 0)
    cr.set_line_width(3)
    cr.move_to(x - size, y)
    cr.line_to(x + size, y)
    cr.move_to(x, y - size)
    cr.line_to(x, y + size)
    cr.stroke()

    # White center
    cr.set_source_rgb(1, 1, 1)
    cr.set_line_width(1)
    cr.move_to(x - size, y)
    cr.line_to(x + size, y)
    cr.move_to(x, y - size)
    cr.line_to(x, y + size)
    cr.stroke()


def draw_selection_overlay(
    cr: cairo.Context,
    x: int,
    y: int,
    width: int,
    height: int,
    img_width: int,
    img_height: int,
):
    """Draw semi-transparent overlay outside the selection area."""
    # Dark overlay outside selection
    cr.set_source_rgba(0, 0, 0, 0.5)
    cr.rectangle(0, 0, img_width, y)  # Top
    cr.rectangle(0, y, x, height)  # Left
    cr.rectangle(x + width, y, img_width - (x + width), height)  # Right
    cr.rectangle(0, y + height, img_width, img_height - (y + height))  # Bottom
    cr.fill()

    # Selection border
    cr.set_source_rgb(0.3, 0.6, 1.0)
    cr.set_line_width(2)
    cr.rectangle(x, y, width, height)
    cr.stroke()


def draw_dimension_text(cr: cairo.Context, x: int, y: int, width: int, height: int):
    """Draw dimension text in the center of a selection."""
    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(14)
    dim_text = f"{width} x {height}"
    extents = cr.text_extents(dim_text)

    text_x = x + width / 2 - extents.width / 2
    text_y = y + height / 2 + extents.height / 2

    # Background
    cr.set_source_rgba(0, 0, 0, 0.8)
    cr.rectangle(
        text_x - 5,
        text_y - extents.height - 5,
        extents.width + 10,
        extents.height + 10,
    )
    cr.fill()

    # Text
    cr.set_source_rgb(1, 1, 1)
    cr.move_to(text_x, text_y)
    cr.show_text(dim_text)


def draw_instructions(cr: cairo.Context, x: int = 20, y: int = 30):
    """Draw help instructions in the corner."""
    instructions = [
        "Click window: Capture window",
        "Drag: Select area",
        "PrintScreen: Full screen",
        "Arrow keys: Fine adjust",
        "ESC/Right-click: Cancel",
    ]

    cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(14)

    for instruction in instructions:
        extents = cr.text_extents(instruction)
        # Background
        cr.set_source_rgba(0, 0, 0, 0.7)
        cr.rectangle(x - 5, y - extents.height - 2, extents.width + 10, extents.height + 6)
        cr.fill()
        # Text
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(x, y)
        cr.show_text(instruction)
        y += 22


def draw_window_highlight(
    cr: cairo.Context,
    window: dict,
    all_windows: list[dict],
    screenshot,
):
    """Draw highlight for hovered window, respecting z-order."""
    import gi
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk

    win_z = window.get("z_order", 999)
    wx, wy = window["x"], window["y"]
    ww, wh = window["width"], window["height"]

    # Collect front windows that overlap with hovered window
    front_windows = []
    for other_win in all_windows:
        if other_win.get("z_order", 999) < win_z:
            ox, oy = other_win["x"], other_win["y"]
            ow, oh = other_win["width"], other_win["height"]
            # Check overlap
            if not (ox >= wx + ww or ox + ow <= wx or oy >= wy + wh or oy + oh <= wy):
                front_windows.append(other_win)

    # Draw highlight, then "erase" front windows by redrawing background
    cr.save()
    cr.rectangle(wx, wy, ww, wh)
    cr.clip()

    # Draw the highlight
    cr.set_source_rgba(0.3, 0.6, 1.0, 0.3)
    cr.paint()

    # Paint screenshot back over front window areas (removes highlight there)
    for other_win in front_windows:
        ox, oy = other_win["x"], other_win["y"]
        ow, oh = other_win["width"], other_win["height"]
        cr.save()
        cr.rectangle(ox, oy, ow, oh)
        cr.clip()
        Gdk.cairo_set_source_pixbuf(cr, screenshot, 0, 0)
        cr.paint()
        cr.restore()

    cr.restore()

    # Draw window border (full border, not clipped)
    cr.set_source_rgb(0.3, 0.6, 1.0)
    cr.set_line_width(3)
    cr.rectangle(wx, wy, ww, wh)
    cr.stroke()
