"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — Event Bus                                               ║
║  ────────────────────────────────────────────────────────────────────    ║
║  In-memory publish/subscribe event router. Decouples the simulator       ║
║  (which emits events) from the agents (which react to them).             ║
║                                                                           ║
║  Design choices:                                                          ║
║    • Synchronous delivery — handlers run in caller's thread, in order    ║
║    • Type-based routing — subscribe by class, not by string topic        ║
║    • Error isolation — one handler's exception doesn't break others     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Callable, Type, Any
from collections import defaultdict
from threading import Lock

logger = logging.getLogger("hephaestus.event_bus")


class EventBus:
    """
    Pub/sub event router.

    Usage:
        bus = EventBus()
        bus.subscribe(CellLifecycleEvent, my_handler)
        bus.publish(CellLifecycleEvent(cell_id="C-001", stage="COATING"))
    """

    def __init__(self):
        self._subscribers: dict[Type, list[Callable]] = defaultdict(list)
        self._lock = Lock()
        self.events_published = 0
        self.events_delivered = 0

    def subscribe(self, event_type: Type, handler: Callable[[Any], None]) -> None:
        """Register a handler to be called for every event of the given type."""
        with self._lock:
            self._subscribers[event_type].append(handler)
            logger.info(
                f"Subscribed handler {handler.__qualname__} to {event_type.__name__}. "
                f"Total subscribers for this type: {len(self._subscribers[event_type])}"
            )

    def publish(self, event: Any) -> None:
        """
        Deliver an event to all subscribers registered for its type.
        Handler exceptions are caught and logged but do not propagate.
        """
        event_type = type(event)
        self.events_published += 1

        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))

        if not handlers:
            logger.debug(f"Published {event_type.__name__} but no subscribers.")
            return

        for handler in handlers:
            try:
                handler(event)
                self.events_delivered += 1
            except Exception as e:
                logger.exception(
                    f"Handler {handler.__qualname__} raised exception "
                    f"processing {event_type.__name__}: {e}"
                )

    def subscriber_count(self, event_type: Type = None) -> int:
        """Return the number of subscribers, optionally filtered by event type."""
        with self._lock:
            if event_type is None:
                return sum(len(handlers) for handlers in self._subscribers.values())
            return len(self._subscribers.get(event_type, []))

    def stats(self) -> dict:
        """Return runtime statistics for the bus. Used by /api/status endpoint."""
        with self._lock:
            return {
                "events_published": self.events_published,
                "events_delivered": self.events_delivered,
                "event_types_registered": len(self._subscribers),
                "total_subscribers": sum(
                    len(handlers) for handlers in self._subscribers.values()
                ),
                "subscribers_by_type": {
                    event_type.__name__: len(handlers)
                    for event_type, handlers in self._subscribers.items()
                },
            }


# Module-level singleton — one shared bus for the whole application.
bus = EventBus()
