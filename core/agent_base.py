"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — Agent Base Class                                        ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Defines the contract every agent must follow. Provides auto-           ║
║  registration with the event bus and a consistent decision-logging      ║
║  interface.                                                              ║
║                                                                           ║
║  Every agent (HERMES, FORGE, THEMIS, and any future agent) extends      ║
║  this class. The infrastructure handles registration; the agent only    ║
║  implements its own logic.                                              ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Type, Any
from datetime import datetime

from core.event_bus import bus

logger = logging.getLogger("hephaestus.agent")


class Agent(ABC):
    """
    Base class for all HEPHAESTUS agents.

    Subclasses must define:
        name (str)              - human-readable agent name (e.g. "FORGE")
        subscribes_to (list)    - event types this agent cares about
        handle(event)           - what to do when an event arrives

    Optional:
        setup()                 - called once at registration time
    """

    # Subclasses MUST override these — Python enforces this via ABC
    name: str = ""
    subscribes_to: List[Type] = []

    def __init__(self):
        # Each agent has its own private state dict.
        # Use this for counters, recent decisions, model references, etc.
        self.state: dict = {}

        # Track basic activity counters automatically — useful for dashboards.
        self.events_handled: int = 0
        self.decisions_logged: int = 0
        self.last_activity: str = "—"
        self.status: str = "IDLE"  # IDLE, ACTIVE, ERROR

        # Run optional setup
        self.setup()

        # Register with the event bus for every event type we care about
        self._register()

        logger.info(f"Agent {self.name} initialized and registered for: "
                    f"{[t.__name__ for t in self.subscribes_to]}")

    def setup(self) -> None:
        """
        Optional hook called once during __init__, before bus registration.
        Override in subclasses to load models, configs, etc.
        Default implementation does nothing.
        """
        pass

    @abstractmethod
    def handle(self, event: Any) -> None:
        """
        Process an event. MUST be implemented by every subclass.

        This method is called by the event bus when a relevant event
        is published. Should be fast (milliseconds) — long-running work
        should be deferred or scheduled.
        """
        raise NotImplementedError

    def _register(self) -> None:
        """Internal: register handler with the bus for each subscribed type."""
        if not self.name:
            raise ValueError(f"{type(self).__name__} must define a non-empty 'name'")
        if not self.subscribes_to:
            logger.warning(f"Agent {self.name} subscribes to nothing — is this intentional?")
            return

        for event_type in self.subscribes_to:
            bus.subscribe(event_type, self._dispatch)

    def _dispatch(self, event: Any) -> None:
        """
        Internal: bus calls this; it bumps counters then forwards to handle().
        Keeping this wrapper means subclasses don't have to remember to
        update counters themselves.
        """
        self.status = "ACTIVE"
        self.last_activity = datetime.now().isoformat()
        try:
            self.handle(event)
            self.events_handled += 1
        except Exception as e:
            self.status = "ERROR"
            logger.exception(f"Agent {self.name} failed handling event: {e}")
            raise
        else:
            self.status = "IDLE"

    def log_decision(
        self,
        action: str,
        rationale: str,
        compliance: str = "OK",
        details: dict = None,
    ) -> dict:
        """
        Standardized way for any agent to record a decision.
        Returns the structured decision dict so callers can also use it.

        This will be wired into the THEMIS audit log in Session 2 final step
        (once state_store is in place). For now it just logs to stdout.
        """
        decision = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.name,
            "action": action,
            "rationale": rationale,
            "compliance": compliance,
            "details": details or {},
        }
        self.decisions_logged += 1
        logger.info(f"[{self.name}] {action}: {rationale}")
        return decision

    def get_status(self) -> dict:
        """Return current agent status for dashboards and /api/status."""
        return {
            "name": self.name,
            "status": self.status,
            "events_handled": self.events_handled,
            "decisions_logged": self.decisions_logged,
            "last_activity": self.last_activity,
            "subscribes_to": [t.__name__ for t in self.subscribes_to],
        }
