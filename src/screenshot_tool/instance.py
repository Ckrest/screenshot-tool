"""Single-instance management and double-tap detection.

This module handles:
- Lock file for single instance enforcement
- Double-tap detection for instant screenshot
- Signal handling for communicating with running instance
"""

import fcntl
import logging
import os
import signal
import time
from pathlib import Path
from typing import Optional, TextIO

from .config import Config

log = logging.getLogger(__name__)


class InstanceManager:
    """Manages single-instance behavior and double-tap detection."""

    def __init__(self, config: Config):
        self.config = config
        self._lock_fd: Optional[TextIO] = None

    def check_double_tap(self) -> bool:
        """Check if this invocation is a double-tap.

        A double-tap occurs when the tool is invoked twice within
        the configured time window (default: 500ms).

        Side effect: Records the current timestamp for future checks.

        Returns:
            True if this is a double-tap, False otherwise
        """
        now_ms = int(time.time() * 1000)
        is_double_tap = False

        double_tap_file = self.config.double_tap_file
        try:
            if double_tap_file.exists():
                last_ms = int(double_tap_file.read_text().strip())
                diff = now_ms - last_ms
                if diff < self.config.double_tap_ms:
                    is_double_tap = True
                    double_tap_file.unlink(missing_ok=True)
                    log.debug("Double-tap detected (diff=%dms)", diff)
        except (ValueError, OSError) as e:
            log.debug("Could not read double-tap file: %s", e)

        # Record this invocation time (unless it was a double-tap)
        if not is_double_tap:
            try:
                double_tap_file.write_text(str(now_ms))
            except OSError as e:
                log.debug("Could not write double-tap file: %s", e)

        return is_double_tap

    def acquire_lock(self) -> bool:
        """Try to acquire the lock file.

        Returns:
            True if lock was acquired (we're the only instance),
            False if another instance is running
        """
        lock_file = self.config.lock_file
        try:
            # Use 'a+' mode to avoid truncating existing file
            self._lock_fd = open(lock_file, "a+")
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Got the lock - write our PID
            self._lock_fd.seek(0)
            self._lock_fd.truncate()
            pid = os.getpid()
            self._lock_fd.write(str(pid))
            self._lock_fd.flush()
            log.debug("Lock acquired, PID=%d", pid)
            return True
        except (IOError, OSError) as e:
            log.debug("Lock acquisition failed: %s", e)
            if self._lock_fd:
                self._lock_fd.close()
                self._lock_fd = None
            return False

    def release_lock(self):
        """Release the lock file."""
        if self._lock_fd:
            try:
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                self._lock_fd.close()
            except (IOError, OSError):
                pass
            self._lock_fd = None

        try:
            self.config.lock_file.unlink(missing_ok=True)
        except OSError:
            pass

    def get_running_pid(self) -> Optional[int]:
        """Get the PID of the running instance, if any.

        Returns:
            PID if another instance is running, None otherwise
        """
        lock_file = self.config.lock_file
        if not lock_file.exists():
            return None

        try:
            pid = int(lock_file.read_text().strip())
            # Check if process exists
            os.kill(pid, 0)
            return pid
        except (ValueError, OSError, ProcessLookupError):
            return None

    def signal_fullscreen(self) -> bool:
        """Signal the running instance to take a fullscreen screenshot.

        Sends SIGUSR1 to the running instance.

        Returns:
            True if signal was sent, False otherwise
        """
        pid = self.get_running_pid()
        if pid is None:
            return False

        try:
            os.kill(pid, signal.SIGUSR1)
            log.debug("Sent SIGUSR1 to PID %d", pid)
            return True
        except OSError as e:
            log.debug("Failed to send signal: %s", e)
            return False

    def kill_running(self) -> bool:
        """Kill the running instance.

        Returns:
            True if instance was killed, False otherwise
        """
        pid = self.get_running_pid()
        if pid is None:
            return False

        try:
            os.kill(pid, signal.SIGTERM)
            # Wait a bit for cleanup
            time.sleep(0.1)
            # Force kill if still running
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            log.debug("Killed PID %d", pid)
            return True
        except OSError as e:
            log.debug("Failed to kill: %s", e)
            return False

    def cleanup_stale_lock(self):
        """Remove lock file if the process is no longer running."""
        if self.get_running_pid() is None:
            try:
                self.config.lock_file.unlink(missing_ok=True)
            except OSError:
                pass
