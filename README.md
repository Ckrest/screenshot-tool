# Screenshot Tool

Screenshot Tool is a persistent GTK4 service for Wayland/Wayfire. It captures a
cursor-free raw frame through `wayland-capture`, presents that frozen frame in a
layer-shell selector, and owns selection, encoding, naming, clipboard, sound,
notifications, and post-save hooks.

## Architecture

`screenshot` is a thin D-Bus client. `screenshot-tool.service` owns
`org.nick.ScreenshotTool`, reloads configuration for every request, and runs a
small state machine:

```text
idle → freezing → selecting → saving → idle
```

The UI is created only while selecting. A second interactive request during
freezing or selecting saves the already frozen frame fullscreen, so no lock
file, command file, timer, or second capture is involved. Explicit window
selection asks the same backend for a true window capture after the overlay has
closed; it never silently crops the desktop frame.

The backend boundary is the versioned `wayland-capture/frame@1` raw JSON
contract. Screenshot Tool validates dimensions, stride, RGBA format, straight
alpha, normal transform, cursor exclusion, and per-output layout before
displaying or saving a frame. Each captured output gets its own layer-shell
surface and viewport into a shared frozen frame, so logical Wayfire geometry is
mapped correctly across scaled and transformed displays.

Window selection joins Wayfire geometry to `wayland-capture` exclusively by
the standard opaque foreign-toplevel identifier. App IDs remain a user-facing
convenience selector; missing identifiers make a window uncapturable instead
of falling back to a same-app or same-title window.

## Install

GTK4, gtk4-layer-shell, PyGObject, `wayland-capture`, `wl-copy`, and an optional
`canberra-gtk-play` must be available. Then run:

```bash
./install-user.sh
```

The installer links the user unit, desktop entry, Wayfire action catalog, and
Settings Hub catalog, enables the service, and starts it. Configuration remains
under `~/.config/screenshot-tool/config.yaml`.

## Usage

```bash
screenshot                              # frozen interactive selector
screenshot --instant                    # fullscreen, wait for result
screenshot --region 100,100,800,600
screenshot --window kitty
screenshot --instant --silent --json
screenshot --status
```

Interactive controls:

| Input | Result |
| --- | --- |
| Drag | Capture region |
| Click | Capture window under pointer |
| Space or PrintScreen | Capture frozen frame fullscreen |
| Arrow keys | Move selection pointer by one image pixel |
| Enter | Confirm the active region or window |
| Escape or right-click | Cancel |

## Output and notifications

Default filenames include capture context, such as
`Screenshot_2026-08-15_14-32-08_Region.png`. Window filenames resolve the
desktop application name where possible; titles are opt-in because they can
expose private content. Files are encoded once and atomically moved into place.
Clipboard MIME follows the selected file format.

Every notification is sent as a distinct Freedesktop notification with
`replaces_id=0`. Before publishing a new one, the service calls the standard
`CloseNotification` method for the previous popup. Notification storage and
history remain entirely the notification server's policy. Clicking the current
notification invokes the standard `org.freedesktop.FileManager1.ShowItems`
interface to reveal the file.

## Configuration

Configuration priority is CLI request, `SCREENSHOT_TOOL_*` environment,
configuration file, then defaults. The persistent service reloads it at request
boundaries, so Settings Hub changes need no restart. See `config.example.yaml`.

Executable post-save hooks in `hooks_dir/on_save.d/` receive:

```text
path width height timestamp
```

## Test

```bash
PYTHONPATH=src pytest -q
```

## License

MIT License. See `LICENSE`.
