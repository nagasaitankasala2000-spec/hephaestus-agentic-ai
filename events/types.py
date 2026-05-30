"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — Typed Event Definitions                                 ║
║  ────────────────────────────────────────────────────────────────────    ║
║  All events that flow through the event bus are defined here as          ║
║  immutable Python dataclasses.                                           ║
║                                                                           ║
║  Design choices:                                                          ║
║    • frozen=True → events are immutable after creation (no surprise     ║
║      mutations between subscribers)                                       ║
║    • Auto-generated event_id and timestamp (can't be forgotten)         ║
║    • version field for forward compatibility (Phase 2 can add fields    ║
║      without breaking Phase 1 agents)                                   ║
║    • Base class for shared fields (Pythonic inheritance pattern)       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


def _new_event_id() -> str:
    """Generate a short, readable unique ID for each event."""
    return f"EVT-{str(uuid.uuid4())[:8].upper()}"


def _now_iso() -> str:
    """Return the current timestamp as an ISO-format string."""
    return datetime.now().isoformat()


# ═══════════════════════════════════════════════════════════════════════
# BASE EVENT — every event type inherits from this
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BaseEvent:
    """
    Shared structure for all events. Never instantiated directly —
    only as a parent class for specific event types.
    """
    event_id: str = field(default_factory=_new_event_id)
    timestamp: str = field(default_factory=_now_iso)
    version: int = 1


# ═══════════════════════════════════════════════════════════════════════
# CELL LIFECYCLE — a cell advances through a production stage
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CellLifecycleEvent(BaseEvent):
    """
    Emitted every time an individual cell moves between production stages.

    Stage names match TLYBS_OPERATIONS.md Stage 1-9 nomenclature:
        MIXING, COATING, CALENDERING, SLITTING, ASSEMBLY,
        ELECTROLYTE_FILL, FORMATION, AGING, GRADING

    Plus terminal states:
        SCRAPPED (rejected at any stage), SHIPPED (passed final grading)
    """
    cell_id: str = ""
    stage: str = ""                # current stage AFTER this transition
    previous_stage: Optional[str] = None  # None for newly created cells
    measurements: dict = field(default_factory=dict)
    line_id: str = "LINE-01"


# ═══════════════════════════════════════════════════════════════════════
# TELEMETRY — sensor reading from a piece of equipment
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TelemetryEvent(BaseEvent):
    """
    Emitted periodically (every few simulated minutes) for each piece
    of active equipment. Used by FORGE for anomaly detection and by
    THEMIS for the audit trail.
    """
    equipment_id: str = ""         # e.g., "COATER-01"
    equipment_type: str = ""       # e.g., "COATER", "CALENDER", "WINDER"
    metrics: dict = field(default_factory=dict)
    # metrics example: {"coating_thickness_um": 78.2, "web_tension_n": 45.1}


# ═══════════════════════════════════════════════════════════════════════
# MATERIAL QUALITY — a material lot is consumed by the line
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class MaterialQualityEvent(BaseEvent):
    """
    Emitted when a new material lot is drawn from inventory for use
    on the production line. HERMES tracks supplier quality variance
    from these events.
    """
    material: str = ""             # e.g., "NCM_811_CATHODE"
    lot_id: str = ""               # e.g., "LOT-2024-A8821"
    supplier: str = ""             # e.g., "Yibin Chemical"
    quality_metrics: dict = field(default_factory=dict)
    # example: {"purity_pct": 99.7, "particle_size_d50_um": 8.2, "moisture_ppm": 45}


# ═══════════════════════════════════════════════════════════════════════
# EQUIPMENT HEALTH — equipment condition changes
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EquipmentHealthEvent(BaseEvent):
    """
    Emitted when a piece of equipment's health crosses a threshold,
    or periodically as health gradually degrades.
    Used by FORGE for predictive maintenance recommendations.
    """
    equipment_id: str = ""
    equipment_type: str = ""
    health_pct: float = 100.0      # 0-100, lower = worse
    status: str = "NOMINAL"        # NOMINAL, DEGRADED, CRITICAL, OFFLINE
    expected_remaining_hours: Optional[float] = None
