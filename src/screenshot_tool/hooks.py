"""Hook system for post-capture events.

Hooks are user-configurable scripts in a directory that ALL run after capture.
This module is generic and portable with no external dependencies.

Directory structure (hooks_dir resolved by platformdirs):
    <hooks_dir>/
    └── on_save.d/
        ├── 10-upload.sh
        ├── 20-backup.sh
        └── 30-notify.sh

Scripts run in sorted order. Each receives: path width height timestamp

Hook scripts should:
- Be executable (chmod +x)
- Handle their own errors gracefully
- Not block for long periods (run async if needed)
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config
    from .output import OutputResult

log = logging.getLogger(__name__)


def run_hooks(hooks_dir: Optional[Path], event: str, *args) -> None:
    """Run all hook scripts for an event.

    Args:
        hooks_dir: Base hooks directory (resolved by platformdirs at runtime)
        event: Event name (e.g., "on_save") - looks for {event}.d/ subdirectory
        *args: Arguments to pass to each script
    """
    if not hooks_dir:
        return

    event_dir = hooks_dir / f"{event}.d"
    if not event_dir.exists() or not event_dir.is_dir():
        return

    # Get all executable scripts, sorted by name
    scripts = sorted(
        f for f in event_dir.iterdir()
        if f.is_file() and not f.name.startswith('.')
    )

    for script in scripts:
        try:
            # Check if executable
            if not script.stat().st_mode & 0o111:
                log.debug("Skipping non-executable: %s", script)
                continue

            # Run in background (non-blocking)
            subprocess.Popen(
                [str(script)] + [str(a) for a in args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.debug("Hook executed: %s", script.name)
        except Exception as e:
            log.warning("Hook %s failed: %s", script.name, e)


def notify_save(result: "OutputResult", config: "Config") -> None:
    """Notify all on_save hooks of a saved screenshot.

    Args:
        result: OutputResult with path, width, height, timestamp
        config: Config object with hooks_dir property
    """
    run_hooks(
        config.hooks_dir,
        "on_save",
        result.path,
        result.width,
        result.height,
        result.timestamp,
    )
