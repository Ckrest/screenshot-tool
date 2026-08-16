"""Managed post-save side effects."""

from __future__ import annotations

import logging
from pathlib import Path

from gi.repository import Gio, GLib

from .models import OutputResult

log = logging.getLogger(__name__)
_children: set[Gio.Subprocess] = set()


def _finished(child: Gio.Subprocess, result) -> None:
    try:
        child.wait_finish(result)
    except GLib.Error as exc:
        log.debug("Screenshot child process failed: %s", exc)
    finally:
        _children.discard(child)


def launch(arguments: list[str]) -> None:
    try:
        child = Gio.Subprocess.new(
            arguments,
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
        )
        _children.add(child)
        child.wait_async(None, _finished)
    except GLib.Error as exc:
        log.debug("Could not launch %s: %s", arguments[0], exc)


def play_sound() -> None:
    launch(["canberra-gtk-play", "-i", "screen-capture"])


def notify_save(result: OutputResult, hooks_dir: Path | None) -> None:
    if not hooks_dir:
        return
    directory = hooks_dir / "on_save.d"
    if not directory.is_dir():
        return
    for script in sorted(directory.iterdir()):
        if (
            script.is_file()
            and not script.name.startswith(".")
            and script.stat().st_mode & 0o111
        ):
            launch(
                [
                    str(script),
                    str(result.path),
                    str(result.width),
                    str(result.height),
                    result.timestamp,
                ]
            )
