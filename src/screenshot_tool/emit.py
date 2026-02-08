"""
Structured event emitter.

Default: JSON lines to stderr (captured by journald, pipeable).
Extensible: call add_handler() to add Redis, database, or custom transports.

This file is vendored per-package. It has NO external dependencies.

Event format (matches Systems infra/events/publisher.py schema):
    {"event_type": "...", "timestamp": "...", "source": {"tool": "..."}, "data": {...}}

Events are always single-line JSON on stderr, distinguishable from log lines.
"""

import json
import sys
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict], None]

_handlers: List[EventHandler] = []
_source: str = "unknown"
_stderr_enabled: bool = True


def configure(source: str, stderr: bool = True) -> None:
    """Set the source name for emitted events. Call once at startup.

    Args:
        source: Source identifier for events
        stderr: Whether to write events to stderr (disable for scripting/MCP)
    """
    global _source, _stderr_enabled
    _source = source
    _stderr_enabled = stderr


def add_handler(handler: EventHandler) -> None:
    """Register an additional event handler (e.g., Redis transport)."""
    _handlers.append(handler)


def remove_handler(handler: EventHandler) -> None:
    """Remove a previously registered handler."""
    if handler in _handlers:
        _handlers.remove(handler)


def emit(
    event_type: str,
    data: Dict[str, Any],
    source: Optional[str] = None,
) -> None:
    """
    Emit a structured event.

    Default: writes one JSON line to stderr.
    Additional handlers receive the same event dict.

    Args:
        event_type: Event type (e.g., "operation.completed")
        data: Event payload
        source: Override source name for this event
    """
    event = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": {
            "tool": source or _source,
        },
        "data": data,
    }

    # Default: structured JSON to stderr (one line per event)
    if _stderr_enabled:
        try:
            line = json.dumps(event, default=str)
            print(line, file=sys.stderr, flush=True)
        except Exception:
            pass

    # Additional handlers (injected by Systems or user at startup)
    for handler in _handlers:
        try:
            handler(event)
        except Exception as exc:
            logger.debug("Event handler error: %s", exc)
