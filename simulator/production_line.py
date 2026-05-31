"""
╔══════════════════════════════════════════════════════════════════════════╗
║  TLYB'S Factory Simulator — Production Line                              ║
║  ────────────────────────────────────────────────────────────────────    ║
║  The 9-stage cell production process model. Owns the equipment and     ║
║  decides what happens to each cell at each stage:                       ║
║    • Records realistic process measurements                              ║
║    • Degrades cell quality based on equipment health                    ║
║    • Probabilistically scraps cells (real factories have ~6-8% scrap)   ║
║    • Assigns final grade (A/B/C) at the GRADING stage                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import random
import logging
from datetime import datetime
from typing import Optional

from simulator.config import (
    STAGES,
    STAGE_DURATIONS_MIN,
    STAGE_FAILURE_RATES,
    EQUIPMENT as EQUIPMENT_CONFIG,
)
from simulator.cell import Cell, STAGE_MEASUREMENT_GENERATORS
from simulator.equipment import Equipment

logger = logging.getLogger("hephaestus.production_line")


class ProductionLine:
    """
    The TLYB'S cell production line — owns all equipment and applies the
    9-stage process to each cell that flows through it.

    Usage:
        line = ProductionLine()
        # cell enters MIXING at start
        # line.try_advance_cell(cell, sim_now) called every tick
        # when cell reaches GRADING and finishes, it's terminal
    """

    def __init__(self):
        # Instantiate one Equipment object per entry in the config
        self.equipment_by_stage: dict[str, list[Equipment]] = {}
        for cfg in EQUIPMENT_CONFIG:
            eq = Equipment(cfg["id"], cfg["type"], cfg["stage"])
            self.equipment_by_stage.setdefault(cfg["stage"], []).append(eq)

        # Build a flat list too, for status reporting
        self.all_equipment: list[Equipment] = [
            eq for eq_list in self.equipment_by_stage.values() for eq in eq_list
        ]

        logger.info(
            f"Production line initialized with {len(self.all_equipment)} equipment units "
            f"across {len(self.equipment_by_stage)} stages."
        )

    # ════════════════════════════════════════════════════════════════════
    # MAIN ENTRY POINT — called by factory.py for each cell each tick
    # ════════════════════════════════════════════════════════════════════

    def try_advance_cell(self, cell: Cell, sim_now: datetime) -> Optional[str]:
        """
        Check whether the cell is ready to advance to its next stage.
        If yes, advance it, run the stage's process, and return the new stage.
        If still in-progress, return None.

        Returns:
            - new_stage (str) if advanced
            - None if still processing in current stage
            - "SCRAPPED" if scrapped during this advance
            - "SHIPPED" if completed final grading
        """
        if cell.is_terminal():
            return None

        # Time the cell has spent in its current stage (in simulated minutes)
        elapsed = (sim_now - cell.current_stage_started_at).total_seconds() / 60.0
        required = STAGE_DURATIONS_MIN.get(cell.current_stage, 60)

        if elapsed < required:
            return None  # not ready yet

        # Cell is ready to advance. First, process current stage's exit logic.
        current = cell.current_stage
        scrapped = self._process_stage_exit(cell, current, sim_now)
        if scrapped:
            return "SCRAPPED"

        # Determine next stage
        try:
            current_index = STAGES.index(current)
        except ValueError:
            logger.error(f"Cell {cell.cell_id} in unknown stage: {current}")
            return None

        if current_index >= len(STAGES) - 1:
            # Already at GRADING — finalize and ship
            self._finalize_grading(cell)
            return "SHIPPED"

        next_stage = STAGES[current_index + 1]
        cell.advance_to(next_stage, sim_now)
        return next_stage

    # ════════════════════════════════════════════════════════════════════
    # STAGE-SPECIFIC PROCESSING
    # ════════════════════════════════════════════════════════════════════

    def _process_stage_exit(self, cell: Cell, stage: str, sim_now: datetime) -> bool:
        """
        Apply the stage's effects to the cell as it exits.
            • Equipment processes the cell (cells_processed += 1)
            • Measurements recorded (realistic stage-specific values)
            • Cell quality degraded based on equipment health
            • Probabilistic scrap check

        Returns True if the cell was scrapped at this stage.
        """
        # 1) Mark all equipment at this stage as having processed a cell.
        #    For stages with multiple machines (e.g., 2 winders at ASSEMBLY),
        #    randomly pick one as the "processing" machine for this cell.
        equipment_at_stage = self.equipment_by_stage.get(stage, [])
        if equipment_at_stage:
            machine = random.choice(equipment_at_stage)
            machine.process_cell()

            # Degrade cell quality based on this machine's health
            quality_loss = (1.0 - machine.quality_impact_factor()) * 0.05
            cell.degrade_quality(quality_loss)

        # 2) Record measurements (if this stage has a generator)
        gen = STAGE_MEASUREMENT_GENERATORS.get(stage)
        if gen:
            measurements = gen(cell.quality_score)
            for key, value in measurements.items():
                cell.record_measurement(stage, key, value)

        # 3) Probabilistic scrap check
        base_failure = STAGE_FAILURE_RATES.get(stage, 0.005)
        # Adjusted failure: low quality cells fail more often
        adjusted_failure = base_failure * (2.0 - cell.quality_score)
        if random.random() < adjusted_failure:
            cell.scrap(stage)
            logger.debug(f"Cell {cell.cell_id} SCRAPPED at {stage} "
                         f"(quality={cell.quality_score:.3f})")
            return True

        return False

    def _finalize_grading(self, cell: Cell) -> None:
        """
        At the end of GRADING, assign a final grade based on quality score.
        Mirrors the industry binning system in TLYBS_OPERATIONS.md Section 3.9.
        """
        q = cell.quality_score
        if q >= 0.92:
            grade = "A"
        elif q >= 0.78:
            grade = "B"
        else:
            grade = "C"
        cell.ship(grade)
        logger.debug(f"Cell {cell.cell_id} SHIPPED grade {grade} (quality={q:.3f})")

    # ════════════════════════════════════════════════════════════════════
    # TIME PROGRESSION FOR EQUIPMENT
    # ════════════════════════════════════════════════════════════════════

    def degrade_equipment(self, sim_hours: float) -> None:
        """Called by factory.py each tick — wear and tear on all machines."""
        for eq in self.all_equipment:
            eq.degrade(sim_hours)

    def get_equipment_snapshots(self) -> list[dict]:
        """Return current state of all equipment, for state_store / dashboard."""
        return [eq.to_dict() for eq in self.all_equipment]
