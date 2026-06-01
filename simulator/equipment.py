"""
╔══════════════════════════════════════════════════════════════════════════╗
║  TLYB'S Factory Simulator — Equipment                                    ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Represents a piece of production-line equipment. Maintains health       ║
║  (degrades with use), reports telemetry (becomes noisier as health      ║
║  drops), and influences cell quality during processing.                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import random
from datetime import datetime
from typing import Optional

from simulator.config import EQUIPMENT_HEALTH_DECAY_PCT_PER_HR


# Status thresholds (health % → status string)
HEALTH_THRESHOLDS = {
    "NOMINAL":  70.0,   # above 70 = nominal
    "DEGRADED": 40.0,   # 40-70 = degraded
    "CRITICAL": 0.01,   # below 40 = critical
    # 0 = OFFLINE
}


class Equipment:
    """
    One piece of production-line equipment.

    Lifecycle:
        Always exists (persistent across cells). Processes cells, accumulates
        wear, occasionally reports telemetry.
    """

    def __init__(self, equipment_id: str, equipment_type: str, stage: str):
        self.equipment_id = equipment_id
        self.equipment_type = equipment_type
        self.stage = stage

        # State
        self.health_pct: float = 100.0
        self.status: str = "NOMINAL"
        self.cells_processed: int = 0
        self.last_telemetry_at: Optional[datetime] = None
        self.last_maintenance_at: Optional[datetime] = None
        self.is_offline: bool = False

    # ════════════════════════════════════════════════════════════════════
    # STATE TRANSITIONS
    # ════════════════════════════════════════════════════════════════════

    def degrade(self, sim_hours_used: float) -> None:
        """
        Reduce health based on active use time.
        Real factories see ~0.05% degradation per hour of active operation.
        """
        if self.is_offline:
            return
        decay = EQUIPMENT_HEALTH_DECAY_PCT_PER_HR * sim_hours_used
        self.health_pct = max(0.0, self.health_pct - decay)
        self._update_status()

    def process_cell(self) -> None:
        """Called by the production line each time a cell passes through."""
        self.cells_processed += 1

    def perform_maintenance(self) -> None:
        """Restore health to 100% — simulates a maintenance window."""
        self.health_pct = 100.0
        self.is_offline = False
        self.last_maintenance_at = datetime.now()
        self._update_status()

    def take_offline(self) -> None:
        """Force the equipment offline (simulated failure)."""
        self.is_offline = True
        self.health_pct = 0.0
        self.status = "OFFLINE"

    def _update_status(self) -> None:
        """Recompute the human-readable status from health_pct."""
        if self.is_offline or self.health_pct <= 0:
            self.status = "OFFLINE"
        elif self.health_pct >= HEALTH_THRESHOLDS["NOMINAL"]:
            self.status = "NOMINAL"
        elif self.health_pct >= HEALTH_THRESHOLDS["DEGRADED"]:
            self.status = "DEGRADED"
        else:
            self.status = "CRITICAL"

    # ════════════════════════════════════════════════════════════════════
    # TELEMETRY
    # ════════════════════════════════════════════════════════════════════

    def current_telemetry(self) -> dict:
        """
        Generate a snapshot of sensor readings for this equipment.
        Variance INCREASES as health DECREASES — degraded equipment is
        noisier. This is the realistic behavior that predictive
        maintenance ML models learn from.
        """
        # noise_factor scales from 1.0 (perfect health) to 4.0 (critical)
        noise_factor = 1.0 + (100.0 - self.health_pct) / 33.0

        if self.equipment_type == "MIXER":
            return {
                "mixer_rpm":           round(random.gauss(85.0, 1.5 * noise_factor), 1),
                "torque_nm":           round(random.gauss(450.0, 12.0 * noise_factor), 1),
                "temperature_c":       round(random.gauss(24.0, 0.8 * noise_factor), 2),
                "vibration_mm_s":      round(random.gauss(2.5, 0.4 * noise_factor), 3),
            }

        if self.equipment_type == "COATER":
            return {
                "slot_die_gap_um":     round(random.gauss(180.0, 1.5 * noise_factor), 2),
                "web_speed_m_min":     round(random.gauss(50.0, 1.2 * noise_factor), 2),
                "drying_temp_c":       round(random.gauss(140.0, 2.5 * noise_factor), 1),
                "web_tension_n":       round(random.gauss(45.0, 1.0 * noise_factor), 2),
            }

        if self.equipment_type == "CALENDER":
            return {
                "roller_force_n_cm":   round(random.gauss(6000.0, 80.0 * noise_factor), 1),
                "roller_temp_c":       round(random.gauss(70.0, 1.5 * noise_factor), 1),
                "web_tension_n":       round(random.gauss(50.0, 1.2 * noise_factor), 2),
            }

        if self.equipment_type == "SLITTER":
            return {
                "blade_sharpness_pct": round(random.gauss(self.health_pct, 1.5), 1),
                "web_speed_m_min":     round(random.gauss(120.0, 3.0 * noise_factor), 1),
                "cut_accuracy_mm":     round(abs(random.gauss(0.0, 0.05 * noise_factor)), 4),
            }

        if self.equipment_type == "WINDER":
            return {
                "winding_tension_n":   round(random.gauss(15.0, 0.4 * noise_factor), 2),
                "winding_speed_rpm":   round(random.gauss(60.0, 1.0 * noise_factor), 1),
                "cycle_time_s":        round(random.gauss(13.0, 0.5 * noise_factor), 2),
            }

        if self.equipment_type == "FILLER":
            return {
                "vacuum_mbar":         round(random.gauss(-980.0, 5.0 * noise_factor), 1),
                "fill_rate_ml_s":      round(random.gauss(1.5, 0.05 * noise_factor), 3),
                "cycle_time_s":        round(random.gauss(240.0, 4.0 * noise_factor), 1),
            }

        if self.equipment_type == "FORMATION":
            return {
                "rack_temperature_c":  round(random.gauss(27.5, 0.5 * noise_factor), 2),
                "channel_voltage_v":   round(random.gauss(3.7, 0.02 * noise_factor), 3),
                "energy_kwh_per_cell": round(random.gauss(0.42, 0.01 * noise_factor), 4),
            }

        if self.equipment_type == "GRADER":
            return {
                "test_cycle_time_s":   round(random.gauss(180.0, 3.0 * noise_factor), 1),
                "sensor_drift_pct":    round(random.gauss(0.0, 0.3 * noise_factor), 3),
            }

        # Fallback for any equipment type not in the list above
        return {"health_pct": round(self.health_pct, 2)}

    # ════════════════════════════════════════════════════════════════════
    # IMPACT ON CELL PROCESSING
    # ════════════════════════════════════════════════════════════════════

    def is_operational(self) -> bool:
        """
        True if the equipment can currently process cells.
        False if FAILED/OFFLINE — production should halt at this stage.
        """
        return (not self.is_offline) and self.status != "CRITICAL"

    def throughput_factor(self) -> float:
        """
        Multiplier on production throughput based on health.
        100% → 1.0 (full speed)
        NOMINAL → ~1.0
        DEGRADED → ~0.7
        CRITICAL → 0.0 (halted)
        OFFLINE → 0.0
        """
        if not self.is_operational():
            return 0.0
        # Linear scaling: 100% health → 1.0, 60% (lower edge of DEGRADED) → 0.7
        return max(0.3, self.health_pct / 100.0)

    def scrap_multiplier(self) -> float:
        """
        Multiplier applied to base stage scrap rate.
        Healthy equipment: 1.0× (normal scrap)
        Degraded equipment: up to 4× scrap rate
        Critical equipment: up to 8× scrap rate
        """
        if self.health_pct >= 90.0:
            return 1.0
        elif self.health_pct >= 60.0:
            # Linear: 90% → 1.0, 60% → 4.0
            return 1.0 + (90.0 - self.health_pct) * 0.1
        else:
            # Linear: 60% → 4.0, 30% → 8.0
            return 4.0 + (60.0 - self.health_pct) * 0.133
    def quality_impact_factor(self) -> float:
        """
        How much this equipment hurts cell quality at its current health.
        Returns a number 0.0–1.0, where 1.0 = no impact (perfect equipment)
        and 0.0 = total quality loss.
        Used by the production line to degrade cell quality_score as cells
        are processed by degraded equipment.
        """
        return self.health_pct / 100.0

    # ════════════════════════════════════════════════════════════════════
    # SERIALIZATION
    # ════════════════════════════════════════════════════════════════════

    def to_dict(self) -> dict:
        """Snapshot for dashboard and state store."""
        return {
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "stage": self.stage,
            "health_pct": round(self.health_pct, 2),
            "status": self.status,
            "cells_processed": self.cells_processed,
            "is_offline": self.is_offline,
            "last_maintenance_at": (
                self.last_maintenance_at.isoformat() if self.last_maintenance_at else None
            ),
        }
