# Screenshot Tool

A feature-rich screenshot utility for Wayland/Wayfire with interactive selection, window capture, and pixel-perfect positioning.

## Features

- **Interactive overlay**: Frozen screen with selection tools
- **Window capture**: Click to capture individual windows (via `ext-image-copy-capture`)
- **Region selection**: Drag to select custom areas with live dimensions
- **Full screen**: Instant capture with hotkey double-tap
- **Magnifier**: 9x9 pixel grid with zoom for precise positioning
- **Arrow keys**: Fine-tune cursor position (1px at a time)
- **Multiple outputs**: Clipboard, notification, sound, JSON metadata

## Installation

### System Dependencies

These must be installed via your system package manager:

```bash
# Arch / Manjaro
sudo pacman -S gtk3 gtk-layer-shell libnotify gobject-introspection cairo

# Debian / Ubuntu
sudo apt install gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 libnotify-dev libgirepository1.0-dev libcairo2-dev
```

### Python Package

```bash
# Clone the repository
git clone https://github.com/Ckrest/screenshot-tool.git
cd screenshot-tool

# Install (includes all Python dependencies)
pip install .

# Ensure wayland-capture is available (or set SCREENSHOT_TOOL_WAYLAND_CAPTURE)
```

## Usage

```bash
# Interactive mode (default)
screenshot

# Instant full screen capture
screenshot --instant

# Capture specific region
screenshot --region 100,100,800,600

# Capture window by app-id
screenshot --window kitty

# Silent mode with JSON output (for scripting)
screenshot --instant --silent --json
```

### Hotkey Setup (Wayfire)

```ini
# ~/.config/wayfire.ini
[command]
binding_screenshot = KEY_SYSRQ
command_screenshot = screenshot
```

**Double-tap** the hotkey for instant fullscreen capture.

### Interactive Controls

| Action | Effect |
|--------|--------|
| **Click** | Capture window under cursor |
| **Drag** | Select custom region |
| **Space/PrintScreen** | Full screen capture |
| **Arrow keys** | Fine-tune cursor (1px) |
| **Enter** | Confirm selection |
| **ESC/Right-click** | Cancel |

## Configuration

Settings via environment variables or `~/.config/screenshot-tool/config.yaml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SCREENSHOT_TOOL_WAYLAND_CAPTURE` | `wayland-capture` | Path to wayland-capture binary |
| `SCREENSHOT_TOOL_DATA_DIR` | platform data dir | Base directory for persistent data |
| `SCREENSHOT_TOOL_CACHE_DIR` | platform cache dir | Base directory for cache files |
| `SCREENSHOT_TOOL_OUTPUT_DIR` | `~/Pictures/screenshots` | Default save location |
| `SCREENSHOT_TOOL_DOUBLE_TAP_MS` | `500` | Double-tap detection window (ms) |

## Dependencies

### System

- **wayland-capture**: Screen/window capture binary (ext-image-copy-capture protocol)
- **wl-copy**: Clipboard integration
- **gtk-layer-shell**: Wayland overlay support
- **libnotify**: Desktop notifications

### Python (installed via pip)

- **PyGObject**: GTK3 bindings
- **pycairo**: Cairo bindings
- **PyYAML**: Configuration loading
- **platformdirs**: XDG directory resolution

### Optional

- **wayfire** (pip): Window geometry support for Wayfire compositor

## Output

Screenshots are saved to `~/Pictures/screenshots/` with timestamp filenames.

JSON output mode (`--json`) returns:
```json
{"path": "/path/to/screenshot.png", "width": 1920, "height": 1080, "timestamp": "2025-01-21T12:00:00"}
```

## License

MIT License - see [LICENSE](LICENSE)
