"""Command-line interface for Screenshot Tool.

Entry point flow:
1. Check for double-tap FIRST (before arg parsing)
2. Parse arguments
3. Route to appropriate mode: instant, region, window, or interactive
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

from .config import Config, get_config
from .instance import InstanceManager
from .capture import fullscreen, region, window, CaptureError
from .output import OutputOptions, save
from .wayfire import hide_cursor, show_cursor

log = logging.getLogger(__name__)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create comprehensive argument parser for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Screenshot Tool for Wayland/Wayfire",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Interactive mode (default)
  %(prog)s --instant                 # Instant full screen capture
  %(prog)s --region 100,100,800,600  # Capture specific region
  %(prog)s --window kitty            # Capture window by app-id
  %(prog)s --instant --silent        # Silent capture (no clipboard/notification/sound)
  %(prog)s --instant --output /tmp/shot.png --json  # Custom output with JSON metadata
  %(prog)s --instant --monitor eDP-1 # Capture specific monitor
""",
    )

    # Capture modes (mutually exclusive)
    capture_group = parser.add_mutually_exclusive_group()
    capture_group.add_argument(
        "--instant",
        action="store_true",
        help="Take instant full screen screenshot (no UI)",
    )
    capture_group.add_argument(
        "--region",
        metavar="X,Y,W,H",
        help="Capture specific region (e.g., 100,100,800,600)",
    )
    capture_group.add_argument(
        "--window",
        metavar="APP_ID",
        help="Capture window by app-id (e.g., kitty, brave-browser)",
    )

    # Output options
    parser.add_argument(
        "--output", "-o",
        metavar="PATH",
        help="Custom output path (default: ~/Pictures/screenshots/screenshot_<timestamp>.png)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["png", "jpg", "jpeg", "webp"],
        default="png",
        help="Output format (default: png)",
    )
    parser.add_argument(
        "--quality", "-q",
        type=int,
        default=90,
        metavar="1-100",
        help="Quality for lossy formats (default: 90)",
    )

    # Behavior options
    parser.add_argument(
        "--no-clipboard",
        action="store_true",
        help="Do not copy to clipboard",
    )
    parser.add_argument(
        "--no-notification",
        action="store_true",
        help="Do not show notification",
    )
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="Do not play shutter sound",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Silent mode: no clipboard, no notification, no sound",
    )

    # Output modes
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print output path to stdout",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output metadata as JSON (path, width, height, timestamp)",
    )

    # Additional options
    parser.add_argument(
        "--delay",
        type=int,
        metavar="MS",
        help="Delay before capture in milliseconds",
    )
    parser.add_argument(
        "--monitor",
        metavar="NAME",
        help="Capture specific monitor (e.g., eDP-1, HDMI-A-1)",
    )

    # Debug
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    return parser


def build_output_options(args: argparse.Namespace) -> OutputOptions:
    """Build OutputOptions from parsed arguments."""
    return OutputOptions(
        output_path=Path(args.output) if args.output else None,
        output_format=args.format,
        quality=args.quality,
        clipboard=not (args.no_clipboard or args.silent),
        notification=not (args.no_notification or args.silent),
        sound=not (args.no_sound or args.silent),
        stdout=args.stdout,
        json_output=args.json,
        silent=args.silent,
    )


def handle_instant_capture(
    args: argparse.Namespace,
    config: Config,
    options: OutputOptions,
) -> int:
    """Handle instant fullscreen capture."""
    try:
        temp_path = fullscreen(monitor=args.monitor, config=config)
        save(temp_path, options, config)
        temp_path.unlink(missing_ok=True)
        return 0
    except CaptureError as e:
        log.error("Capture failed: %s", e)
        return 1


def handle_region_capture(
    args: argparse.Namespace,
    config: Config,
    options: OutputOptions,
) -> int:
    """Handle region capture."""
    try:
        parts = args.region.split(",")
        x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    except (ValueError, IndexError):
        log.error("Invalid region format. Use X,Y,W,H (e.g., 100,100,800,600)")
        return 1

    try:
        temp_path = region(x, y, w, h, config=config)
        save(temp_path, options, config)
        temp_path.unlink(missing_ok=True)
        return 0
    except CaptureError as e:
        log.error("Capture failed: %s", e)
        return 1


def handle_window_capture(
    args: argparse.Namespace,
    config: Config,
    options: OutputOptions,
) -> int:
    """Handle window capture."""
    try:
        temp_path = window(args.window, config=config)
        save(temp_path, options, config)
        temp_path.unlink(missing_ok=True)
        return 0
    except CaptureError as e:
        log.error("Capture failed: %s", e)
        return 1


def handle_interactive(config: Config, instance_mgr: InstanceManager) -> int:
    """Handle interactive mode."""
    # Check if already running
    if not instance_mgr.acquire_lock():
        # Already running - signal it to take fullscreen screenshot
        log.debug("Already running, sending signal")
        if instance_mgr.signal_fullscreen():
            return 0
        else:
            log.error("Failed to signal running instance")
            return 1

    try:
        # Import here to avoid GTK initialization for non-interactive modes
        from .ui import run_interactive
        return run_interactive(config)
    finally:
        instance_mgr.release_lock()


def main(args: Optional[list[str]] = None) -> int:
    """Main entry point.

    Args:
        args: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code
    """
    config = get_config()
    instance_mgr = InstanceManager(config)

    # STEP 1: Parse arguments first
    parser = create_argument_parser()
    parsed_args = parser.parse_args(args)

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if parsed_args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # STEP 2: Check for double-tap ONLY when no explicit capture mode
    # Double-tap is a hotkey feature for interactive mode, not for CLI with explicit args
    has_explicit_mode = parsed_args.instant or parsed_args.region or parsed_args.window
    if not has_explicit_mode and instance_mgr.check_double_tap():
        log.debug("Double-tap detected - instant screenshot")
        # Kill any running UI first
        instance_mgr.kill_running()
        instance_mgr.cleanup_stale_lock()

        # Take instant screenshot with cursor hidden
        hide_cursor()
        try:
            temp_path = fullscreen(config=config)
            save(temp_path, OutputOptions())
            temp_path.unlink(missing_ok=True)
        finally:
            show_cursor()
        return 0

    # Handle delay
    if parsed_args.delay:
        time.sleep(parsed_args.delay / 1000.0)

    # Build output options
    options = build_output_options(parsed_args)

    # STEP 3: Route to appropriate mode
    if parsed_args.region:
        return handle_region_capture(parsed_args, config, options)

    if parsed_args.window:
        return handle_window_capture(parsed_args, config, options)

    if parsed_args.instant:
        return handle_instant_capture(parsed_args, config, options)

    # Default: interactive mode
    # Hide cursor before starting interactive mode
    hide_cursor()
    try:
        return handle_interactive(config, instance_mgr)
    finally:
        show_cursor()


if __name__ == "__main__":
    sys.exit(main())
