"""In-process event bus.

A single publish point for domain lifecycle events (certificate.issued,
ca.deleted, ...). Subscribers (webhook delivery, WebSocket push, email
notifications, audit) register once and receive every matching event, so the
lifecycle code emits ONE event instead of calling three notification systems
by hand at every call site.

Design notes:
  * Synchronous dispatch — handlers are expected to be cheap (enqueue a row,
    push a WS frame). Slow work (HTTP delivery) must be deferred by the
    handler itself, not done inline.
  * Fully isolated — a failing/throwing handler can never break ``emit`` or
    the business operation that triggered it.
"""
import logging
import threading
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Wildcard subscription key — a handler registered here receives every event.
ALL = '*'

EventHandler = Callable[[str, dict, Optional[str]], None]


class EventBus:
    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register *handler* for *event_type* (use ALL for every event)."""
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, event_type: str, payload: dict, ca_refid: str = None) -> None:
        """Publish an event. Never raises."""
        with self._lock:
            handlers = list(self._handlers.get(event_type, ())) + list(self._handlers.get(ALL, ()))
        for handler in handlers:
            try:
                handler(event_type, payload, ca_refid)
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Event handler failed for {event_type}: {e}", exc_info=True)


# Global singleton
event_bus = EventBus()
