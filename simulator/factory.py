"""
╔══════════════════════════════════════════════════════════════════════════╗
║  TLYB'S Factory Simulator — Main Loop                                    ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Heartbeat of the gigafactory. Runs in a background thread.              ║
║                                                                           ║
║  Each tick (1 real second by default):                                   ║
║    1. Advance simulated time                                             ║
║    2. Maybe inject a new cell at MIXING                                  ║
║    3. Try to advance every cell in flight                                ║
║    4. Degrade equipment based on elapsed time                            ║
║    5. Emit events for stage transitions, telemetry, scrap, ship          ║
║    6. Clean up terminal cells                                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import time
import random
import logging
import threading
from datetime import datetime, timedelta

from core.event_bus import bus
from core.state_store import store
from events.types import (
    CellLifecycleEvent,
    TelemetryEvent,
    EquipmentHealthEvent,
)
from simulator.config import (
    SIM_MINUTES_PER_TICK,
    TICK_INTERVAL_SECONDS,
    MAX_CELLS_IN_FLIGHT,
    NEW_CELLS_PER_SIM_HOUR,
)
from simulator.cell import Cell
from simulator.production_line import ProductionLine

logger = logging.getLogger("hephaestus.factory")


# Telemetry frequency: each piece of equipment publishes telemetry roughly
# every N simulated minutes. Prevents event bus flooding.
TELEMETRY_INTERVAL_SIM_MIN = 15


class Factory:
    """
    The TLYB'S gigafactory simulator.

    Lifecycle:
        factory = Factory()
        factory.start()      # spawns background thread
        ...                  # everything else runs as normal
        factory.stop()       # graceful shutdown
    """

    def __init__(self):
        self.line = ProductionLine()
        self.cells_in_flight: list[Cell] = []
        self.completed_count = 0
        self.scrapped_count = 0
        self.shipped_count = 0

        # Time tracking
        self.sim_now: datetime = datetime.now()
        self.start_time: datetime = datetime.now()
        self.ticks_run: int = 0

        # Background thread machinery
        self._thread: threading.Thread = None
        self._stop_event = threading.Event()
        self._running = False

        # Throttle telemetry emission
        self._last_telemetry_sim_time: datetime = self.sim_now

        # Cell injection rate-keeper
        self._cells_injected_this_hour = 0
        self._current_sim_hour = self.sim_now.hour

    # ════════════════════════════════════════════════════════════════════
    # LIFECYCLE
    # ════════════════════════════════════════════════════════════════════

    def start(self) -> None:
        """Spawn the background thread and begin ticking."""
        if self._running:
            logger.warning("Factory already running.")
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="FactoryLoop")
        self._thread.start()
        logger.info(f"🏭 TLYB'S Factory started. Sim time compression: "
                    f"{SIM_MINUTES_PER_TICK} sim-min per real-sec.")

    def stop(self) -> None:
        """Signal the loop to stop and wait for the thread to exit."""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("🏭 TLYB'S Factory stopped.")

    def is_running(self) -> bool:
        return self._running

    # ════════════════════════════════════════════════════════════════════
    # MAIN LOOP
    # ════════════════════════════════════════════════════════════════════

    def _run_loop(self) -> None:
        """Internal: the background loop. Don't call directly."""
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                logger.exception(f"Factory tick error: {e}")
            self._stop_event.wait(TICK_INTERVAL_SECONDS)

    def tick(self) -> None:
        """
        Run ONE simulation step. Public so it's testable without threads.
        """
        # 1. Advance simulated time
        sim_minutes_elapsed = SIM_MINUTES_PER_TICK
        self.sim_now += timedelta(minutes=sim_minutes_elapsed)
        sim_hours_elapsed = sim_minutes_elapsed / 60.0

        # 2. Maybe inject a new cell at MIXING
        self._maybe_inject_cell()

        # 3. Advance every cell in flight
        self._advance_cells()

        # 4. Equipment wear
        self.line.degrade_equipment(sim_hours_elapsed)

        # 5. Emit telemetry periodically
        if (self.sim_now - self._last_telemetry_sim_time).total_seconds() / 60.0 >= TELEMETRY_INTERVAL_SIM_MIN:
            self._emit_telemetry()
            self._last_telemetry_sim_time = self.sim_now

        # 6. Push updated equipment health to the state store
        self._publish_equipment_health()

        # 7. Push factory-level metrics to the state store
        self._publish_factory_status()

        self.ticks_run += 1

    # ════════════════════════════════════════════════════════════════════
    # CELL INJECTION
    # ════════════════════════════════════════════════════════════════════

    def _maybe_inject_cell(self) -> None:
        """Decide whether to start a new cell this tick."""
        # Reset hour-bucket counter when sim_now crosses an hour
        if self.sim_now.hour != self._current_sim_hour:
            self._current_sim_hour = self.sim_now.hour
            self._cells_injected_this_hour = 0

        # Don't exceed line capacity
        if len(self.cells_in_flight) >= MAX_CELLS_IN_FLIGHT:
            return

        # Don't exceed target rate per simulated hour
        if self._cells_injected_this_hour >= NEW_CELLS_PER_SIM_HOUR:
            return

        # Inject a cell with high probability each tick
        # (this gives a smooth flow rather than all-at-once-per-hour)
        target_per_tick = NEW_CELLS_PER_SIM_HOUR / (60.0 / SIM_MINUTES_PER_TICK)
        if random.random() < target_per_tick:
            self._inject_cell()

    def _inject_cell(self) -> None:
        """Create a new cell at MIXING and emit the creation event."""
        cell = Cell()
        cell.advance_to("MIXING", self.sim_now)
        self.cells_in_flight.append(cell)
        self._cells_injected_this_hour += 1

        bus.publish(CellLifecycleEvent(
            cell_id=cell.cell_id,
            stage="MIXING",
            previous_stage=None,
            measurements={},
        ))

    # ════════════════════════════════════════════════════════════════════
    # CELL ADVANCEMENT
    # ════════════════════════════════════════════════════════════════════

    def _advance_cells(self) -> None:
        """Try to advance every cell in flight. Emit events for transitions."""
        still_in_flight: list[Cell] = []
        for cell in self.cells_in_flight:
            previous_stage = cell.current_stage
            result = self.line.try_advance_cell(cell, self.sim_now)

            if result is None:
                # Still in progress at current stage
                still_in_flight.append(cell)
                continue

            if result == "SCRAPPED":
                # Cell scrapped at this stage
                self.scrapped_count += 1
                self.completed_count += 1
                bus.publish(CellLifecycleEvent(
                    cell_id=cell.cell_id,
                    stage="SCRAPPED",
                    previous_stage=previous_stage,
                    measurements=cell.measurements.get(previous_stage, {}),
                ))
                # Don't keep in flight
                continue

            if result == "SHIPPED":
                # Cell finished GRADING successfully
                self.shipped_count += 1
                self.completed_count += 1
                bus.publish(CellLifecycleEvent(
                    cell_id=cell.cell_id,
                    stage="SHIPPED",
                    previous_stage=previous_stage,
                    measurements=cell.measurements.get("GRADING", {}),
                ))
                continue

            # result is a new stage name — cell advanced normally
            bus.publish(CellLifecycleEvent(
                cell_id=cell.cell_id,
                stage=result,
                previous_stage=previous_stage,
                measurements=cell.measurements.get(previous_stage, {}),
            ))
            still_in_flight.append(cell)

        self.cells_in_flight = still_in_flight

    # ════════════════════════════════════════════════════════════════════
    # TELEMETRY EMISSION
    # ════════════════════════════════════════════════════════════════════

    def _emit_telemetry(self) -> None:
        """Each active machine publishes a telemetry event."""
        for eq in self.line.all_equipment:
            if eq.is_offline:
                continue
            bus.publish(TelemetryEvent(
                equipment_id=eq.equipment_id,
                equipment_type=eq.equipment_type,
                metrics=eq.current_telemetry(),
            ))

    # ════════════════════════════════════════════════════════════════════
    # STATE STORE UPDATES
    # ════════════════════════════════════════════════════════════════════

    def _publish_equipment_health(self) -> None:
        """Update equipment health snapshots in the state store."""
        for eq in self.line.all_equipment:
            store.update_equipment_health(eq.equipment_id, eq.to_dict())
            # Emit a health event ONLY when status crosses a threshold —
            # i.e., on visible transitions. (Cheap dedup using last status.)
            # For Phase 1 we emit every tick — overhead is minimal.
            bus.publish(EquipmentHealthEvent(
                equipment_id=eq.equipment_id,
                equipment_type=eq.equipment_type,
                health_pct=eq.health_pct,
                status=eq.status,
            ))

    def _publish_factory_status(self) -> None:
        """Push aggregated factory metrics into the state store."""
        store.update_yield_metric("cells_produced_today", self.shipped_count)
        store.update_yield_metric("cells_scrapped_today", self.scrapped_count)
        if self.completed_count > 0:
            yield_pct = 100.0 * self.shipped_count / self.completed_count
            store.update_yield_metric("current_yield_pct", round(yield_pct, 2))

    # ════════════════════════════════════════════════════════════════════
    # INTROSPECTION (for /api/simulator/status endpoint)
    # ════════════════════════════════════════════════════════════════════

    def status(self) -> dict:
        """Return current factory state for the dashboard / status endpoint."""
        return {
            "running": self._running,
            "sim_now": self.sim_now.isoformat(),
            "real_started_at": self.start_time.isoformat(),
            "ticks_run": self.ticks_run,
            "cells_in_flight": len(self.cells_in_flight),
            "cells_shipped": self.shipped_count,
            "cells_scrapped": self.scrapped_count,
            "cells_completed": self.completed_count,
            "current_yield_pct": (
                round(100.0 * self.shipped_count / self.completed_count, 2)
                if self.completed_count > 0 else None
            ),
            "equipment": self.line.get_equipment_snapshots(),
        }


# ─────────────────────────────────────────────────────────────────────────
# Module-level singleton — one factory per process
# ─────────────────────────────────────────────────────────────────────────
factory = Factory()
