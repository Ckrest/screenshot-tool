"""Thin D-Bus client for the persistent Screenshot Tool service."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from gi.repository import Gio, GLib

from . import __version__
from .config import (
    config_defaults,
    config_schema,
    config_to_dict,
    load_config,
    validate_config_file,
)
from .dbus_api import BUS_NAME, INTERFACE, OBJECT_PATH


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Screenshot Tool for Wayland/Wayfire")
    parser.add_argument(
        "--version", action="version", version=f"screenshot-tool {__version__}"
    )
    parser.add_argument("--config", metavar="PATH")
    parser.add_argument("--print-defaults", action="store_true")
    parser.add_argument("--print-config-schema", action="store_true")
    parser.add_argument("--validate-config", action="store_true")
    parser.add_argument("--print-resolved", action="store_true")
    parser.add_argument("--print-hook-contract", action="store_true")
    parser.add_argument("--print-event-catalog", action="store_true")
    parser.add_argument("--print-lifecycle", action="store_true")
    parser.add_argument("--list-windows", action="store_true")
    parser.add_argument("--status", action="store_true", help="Show the service state")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--instant",
        action="store_true",
        help="Capture fullscreen without opening the UI",
    )
    modes.add_argument("--region", metavar="X,Y,W,H")
    modes.add_argument("--window", metavar="APP_ID")
    parser.add_argument("--output", "-o", metavar="PATH")
    parser.add_argument("--format", "-f", choices=["png", "jpg", "jpeg", "webp"])
    parser.add_argument("--quality", "-q", type=int, metavar="1-100")
    parser.add_argument("--no-clipboard", action="store_true")
    parser.add_argument("--no-notification", action="store_true")
    parser.add_argument("--no-sound", action="store_true")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--delay", type=int, metavar="MS", default=0)
    parser.add_argument("--monitor", metavar="NAME")
    parser.add_argument("--debug", action="store_true")
    return parser


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _introspection(args) -> int | None:
    config_path = Path(args.config).expanduser() if args.config else None
    if args.print_defaults:
        _print(config_defaults())
        return 0
    if args.print_config_schema:
        _print(config_schema())
        return 0
    if args.validate_config:
        errors = validate_config_file(config_path)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        return 0
    if args.print_resolved:
        _print(config_to_dict(load_config(config_path)))
        return 0
    if args.print_hook_contract:
        _print(
            {
                "events": [
                    {
                        "name": "on_save",
                        "args": ["output_path", "width", "height", "timestamp"],
                    }
                ]
            }
        )
        return 0
    if args.print_event_catalog:
        _print({"signals": ["Completed", "Failed"], "interface": INTERFACE})
        return 0
    if args.print_lifecycle:
        _print({"states": ["idle", "freezing", "selecting", "saving"]})
        return 0
    if args.list_windows:
        from .window import enumerate_windows

        _print(
            {
                "windows": [
                    {
                        "app_id": w.app_id,
                        "title": w.title,
                        "capture_id": w.capture_id,
                        "view_id": w.view_id,
                        "geometry": w.geometry,
                    }
                    for w in enumerate_windows(load_config(config_path))
                ]
            }
        )
        return 0
    return None


def _proxy() -> Gio.DBusProxy:
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION,
        Gio.DBusProxyFlags.NONE,
        None,
        BUS_NAME,
        OBJECT_PATH,
        INTERFACE,
        None,
    )


def _state(proxy: Gio.DBusProxy) -> dict[str, Any]:
    return proxy.call_sync(
        "GetState", None, Gio.DBusCallFlags.NONE, 5000, None
    ).unpack()[0]


def _request_values(args, request_id: str | None = None) -> dict[str, GLib.Variant]:
    mode = (
        "fullscreen"
        if args.instant
        else "region"
        if args.region
        else "window"
        if args.window
        else "interactive"
    )
    values: dict[str, Any] = {
        "mode": mode,
        "delay_ms": max(0, args.delay),
        "silent": args.silent,
    }
    if request_id:
        values["request_id"] = request_id
    for key, value in {
        "region": args.region,
        "window": args.window,
        "monitor": args.monitor,
        "output": args.output,
        "format": args.format,
        "quality": args.quality,
        "config_path": args.config,
    }.items():
        if value is not None:
            values[key] = value
    if args.no_clipboard:
        values["clipboard"] = False
    if args.no_notification:
        values["notification"] = False
    if args.no_sound:
        values["sound"] = False
    variants = {}
    for key, value in values.items():
        if isinstance(value, bool):
            variants[key] = GLib.Variant("b", value)
        elif isinstance(value, int):
            variants[key] = GLib.Variant("x", value)
        else:
            variants[key] = GLib.Variant("s", str(value))
    return variants


def _capture(proxy: Gio.DBusProxy, args) -> int:
    wait = bool(
        args.instant
        or args.region
        or args.window
        or args.stdout
        or args.json
        or args.output
    )
    loop = GLib.MainLoop() if wait else None
    outcome: dict[str, Any] = {"request_id": str(uuid.uuid4())}

    def signal(_proxy, _sender, name, parameters):
        values = parameters.unpack()
        if values[0] != outcome["request_id"]:
            return
        if name == "Completed":
            outcome["result"] = values[1]
        elif name == "Failed":
            outcome["error"] = f"{values[1]}: {values[2]}"
        if loop:
            loop.quit()

    proxy.connect("g-signal", signal)
    reply = proxy.call_sync(
        "Request",
        GLib.Variant("(a{sv})", (_request_values(args, outcome["request_id"]),)),
        Gio.DBusCallFlags.NONE,
        5000,
        None,
    )
    if reply.unpack()[0] != outcome["request_id"]:
        print(
            "Screenshot service returned a mismatched request identifier",
            file=sys.stderr,
        )
        return 1
    if not wait:
        return 0
    GLib.timeout_add_seconds(
        60,
        lambda: (
            outcome.setdefault("error", "Timed out waiting for screenshot"),
            loop.quit(),
            GLib.SOURCE_REMOVE,
        )[2],
    )
    loop.run()
    if "error" in outcome:
        print(outcome["error"], file=sys.stderr)
        return 1
    result = outcome["result"]
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif args.stdout or args.output or args.silent:
        print(result["path"])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = create_argument_parser().parse_args(argv)
    result = _introspection(args)
    if result is not None:
        return result
    try:
        proxy = _proxy()
        if args.status:
            _print(_state(proxy))
            return 0
        return _capture(proxy, args)
    except GLib.Error as exc:
        print(f"Screenshot service unavailable: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
