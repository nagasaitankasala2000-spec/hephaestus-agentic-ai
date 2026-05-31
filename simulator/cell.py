"""
╔══════════════════════════════════════════════════════════════════════════╗
║  TLYB'S Factory Simulator — Cell Lifecycle                               ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Represents one battery cell as it moves through the 9-stage production  ║
║  process. Mutable: advances stages, accumulates measurements, eventually ║
║  reaches a terminal state (SHIPPED or SCRAPPED).                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import uuid
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


def _new_cell_id() -> str:
    """Generate a short, readable cell ID like 'C-A1B2C3'."""
    return f"C-{str(uuid.uuid4())[:6].upper()}"


@dataclass
class Cell:
    """
    One battery cell flowing through the production line.

    Lifecycle:
        Created → MIXING → COATING → ... → GRADING → (SHIPPED or SCRAPPED)
    """

    # Identity
    cell_id: str = field(default_factory=_new_cell_id)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Current state
    current_stage: str = "MIXING"
    current_stage_started_at: datetime = field(default_factory=datetime.now)
    line_id: str = "LINE-01"

    # Measurements taken at each stage — populated as the cell advances.
    # Structure: {"COATING": {"thickness_um": 78.5, ...}, "CALENDERING": {...}}
    measurements: dict = field(default_factory=dict)

    # Terminal state — only set when the cell exits the line.
    final_status: Optional[str] = None  # "SHIPPED", "SCRAPPED", or None
    final_grade: Optional[str] = None   # "A", "B", "C", or None
    scrapped_at_stage: Optional[str] = None

    # Quality score — running variable updated by the production line.
    # Starts at 1.0 (perfect); degrades based on process variance.
    # Used at GRADING to determine final disposition.
    quality_score: float = 1.0

    def advance_to(self, new_stage: str, sim_now: datetime) -> None:
        """Move the cell to its next stage, recording the transition."""
        self.current_stage = new_stage
        self.current_stage_started_at = sim_now

    def record_measurement(self, stage: str, key: str, value) -> None:
        """Add a measurement taken at the given stage."""
        if stage not in self.measurements:
            self.measurements[stage] = {}
        self.measurements[stage][key] = value

    def degrade_quality(self, amount: float) -> None:
        """Reduce quality score (called when process variance is high at a stage)."""
        self.quality_score = max(0.0, self.quality_score - amount)

    def ship(self, grade: str) -> None:
        """Mark cell as successfully shipped at the given grade."""
        self.final_status = "SHIPPED"
        self.final_grade = grade

    def scrap(self, at_stage: str) -> None:
        """Mark cell as scrapped at the given stage."""
        self.final_status = "SCRAPPED"
        self.scrapped_at_stage = at_stage

    def is_terminal(self) -> bool:
        """True once the cell has exited the line (shipped or scrapped)."""
        return self.final_status is not None

    def to_dict(self) -> dict:
        """Serialize to a dict — useful for the dashboard."""
        return {
            "cell_id": self.cell_id,
            "current_stage": self.current_stage,
            "quality_score": round(self.quality_score, 4),
            "measurements_stages": list(self.measurements.keys()),
            "final_status": self.final_status,
            "final_grade": self.final_grade,
            "scrapped_at_stage": self.scrapped_at_stage,
            "created_at": self.created_at,
        }


# ════════════════════════════════════════════════════════════════════════
# HELPER — generate realistic process measurements for a cell at a stage
# ════════════════════════════════════════════════════════════════════════
# These distributions are grounded in published battery research (per
# TLYBS_OPERATIONS.md Section 3). The simulator calls these helpers when
# a cell exits each stage to record what "happened" to it.

def generate_coating_measurements(quality_score: float) -> dict:
    """
    Coating stage produces electrode foil with a target thickness.
    Lower quality_score → more variance from target.

    Target: 78 μm (per ops doc)
    Acceptable range: 60-90 μm
    """
    variance = 1.5 + (1.0 - quality_score) * 8.0  # higher variance when quality is low
    return {
        "thickness_um": round(random.gauss(78.0, variance), 2),
        "uniformity_cv": round(random.uniform(0.5, 2.5) * (2.0 - quality_score), 3),
        "areal_mass_mg_cm2": round(random.gauss(22.0, 0.8), 2),
        "defect_density_per_m2": round(random.expovariate(1.0 / (0.5 + (1 - quality_score) * 3)), 2),
    }


def generate_calendering_measurements(quality_score: float) -> dict:
    """
    Calendering compresses the coated electrode to a target density.
    Target: 3.5 g/cm³ for cathode, 30% porosity.
    """
    return {
        "density_g_cm3": round(random.gauss(3.5, 0.05), 3),
        "porosity_pct": round(random.gauss(30.0, 1.5), 2),
        "calender_force_n_cm": round(random.gauss(6000, 200), 1),
    }


def generate_slitting_measurements(quality_score: float) -> dict:
    """Slitting cuts the wide electrode into strips."""
    return {
        "edge_burr_um": round(random.gauss(3.0, 1.0) * (2.0 - quality_score), 2),
        "width_accuracy_mm": round(abs(random.gauss(0.0, 0.05)), 4),
    }


def generate_assembly_measurements(quality_score: float) -> dict:
    """Assembly winds the jelly roll and welds the can."""
    return {
        "winding_tension_n": round(random.gauss(15.0, 0.5), 2),
        "weld_strength_n": round(random.gauss(180.0, 8.0), 1),
        "initial_resistance_mohm": round(random.gauss(12.0, 0.8), 2),
    }


def generate_fill_measurements(quality_score: float) -> dict:
    """Electrolyte fill — volume and seal integrity."""
    return {
        "electrolyte_volume_ml": round(random.gauss(15.0, 0.2), 3),
        "seal_pressure_psi": round(random.gauss(120.0, 4.0), 1),
        "post_fill_weight_g": round(random.gauss(70.0, 0.5), 2),
    }


def generate_formation_measurements(quality_score: float) -> dict:
    """Formation cycling — SEI layer formation, the critical step."""
    return {
        "coulombic_efficiency": round(random.gauss(0.92, 0.015) * quality_score, 4),
        "first_cycle_capacity_ah": round(random.gauss(15.0, 0.3), 3),
        "internal_resistance_mohm": round(random.gauss(10.0, 0.6), 2),
    }


def generate_grading_measurements(quality_score: float) -> dict:
    """Final grading — full electrical characterization."""
    return {
        "rated_capacity_ah": round(random.gauss(14.8, 0.25) * quality_score, 3),
        "self_discharge_mv_day": round(random.expovariate(1.0 / 2.0), 2),
        "dc_resistance_mohm": round(random.gauss(9.5, 0.4), 2),
    }


# Map stages to their measurement generators — used by production_line.py
STAGE_MEASUREMENT_GENERATORS = {
    "COATING":          generate_coating_measurements,
    "CALENDERING":      generate_calendering_measurements,
    "SLITTING":         generate_slitting_measurements,
    "ASSEMBLY":         generate_assembly_measurements,
    "ELECTROLYTE_FILL": generate_fill_measurements,
    "FORMATION":        generate_formation_measurements,
    "GRADING":          generate_grading_measurements,
}
