"""Single-instance management.

This module handles:
- Lock file for single instance enforcement
- Signal handling for communicating with running instance
"""

import fcntl
import logging
import os
import signal
from typing import Optional, TextIO

from .config import Config

log = logging.getLogger(__name__)


class InstanceManager:
    """Manages single-instance behavior."""

    def __init__(self, config: Config):
        self.config = config
        self._lock_fd: Optional[TextIO] = None

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

    def cleanup_stale_lock(self):
        """Remove lock file if the process is no longer running."""
        if self.get_running_pid() is None:
            try:
                self.config.lock_file.unlink(missing_ok=True)
            except OSError:
                pass
