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
    MaterialQualityEvent,
)
from simulator.config import (
    SIM_MINUTES_PER_TICK,
    TICK_INTERVAL_SECONDS,
    MAX_CELLS_IN_FLIGHT,
    NEW_CELLS_PER_SIM_HOUR,
    MATERIALS,
    SUPPLIERS,
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
# ── Material tracking (v2 HERMES integration) ─────────────
        # Counter for batch material events — emits every BATCH_SIZE_CELLS
        self._cells_since_last_batch = 0
        # How many cells per material batch event
        self.BATCH_SIZE_CELLS = 100
        # Auto-maintenance schedule (until manual controls exist)
        self.MAINTENANCE_INTERVAL_TICKS = 120  # 120 ticks = 5 sim-days
        self._ticks_since_last_maintenance = 0
        # Pick a current supplier per material (HERMES can override)
        self._current_supplier_per_material = {}
        self._material_lot_counter = 0
        # Initialize inventory in state store
        for mat_name, mat_info in MATERIALS.items():
            # Start with enough inventory for ~500 cells per material
            initial_qty = mat_info["consumption_per_cell"] * 500
            store.set_material_inventory(mat_name, initial_qty)
        # Pick first supplier per material as default
        for mat_name, supplier_list in SUPPLIERS.items():
            if supplier_list:
                self._current_supplier_per_material[mat_name] = supplier_list[0]

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
        # Material batch tracking (v2 HERMES integration)
        self._cells_since_last_batch += 1
        self._maybe_emit_material_batch()
# Auto-maintenance every ~5 sim-days (until manual controls exist)
        self._maybe_perform_maintenance()
# ── Snapshot metrics for time-series dashboard (v2) ───────────
        self._maybe_snapshot_metrics()

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

    def _maybe_emit_material_batch(self) -> None:
        """
        Every BATCH_SIZE_CELLS produced, emit one MaterialQualityEvent
        per material, representing one lot consumed. Includes realistic
        supplier-specific quality variance.
        """
        if self._cells_since_last_batch < self.BATCH_SIZE_CELLS:
            return

        import random
        # Emit one event per material we have supplier data for
        for mat_name, supplier_list in SUPPLIERS.items():
            if not supplier_list:
                continue
            supplier = self._current_supplier_per_material.get(mat_name, supplier_list[0])
            self._material_lot_counter += 1
            lot_id = f"LOT-{self.sim_now.strftime('%Y%m')}-{self._material_lot_counter:05d}"

            # Generate quality measurement based on supplier mean/stddev
            quality_pct = random.gauss(
                supplier["quality_mean"],
                supplier["quality_stddev"],
            )
            quality_pct = max(95.0, min(100.0, quality_pct))

            # Draw down inventory (BATCH_SIZE_CELLS worth)
            consumption_per_cell = MATERIALS[mat_name]["consumption_per_cell"]
            total_consumed = consumption_per_cell * self.BATCH_SIZE_CELLS
            new_inventory = store.adjust_material_inventory(mat_name, -total_consumed)

            # Publish the event
            bus.publish(MaterialQualityEvent(
                material=mat_name,
                lot_id=lot_id,
                supplier=supplier["name"],
                quality_metrics={
                    "purity_pct": round(quality_pct, 3),
                    "consumed_quantity": round(total_consumed, 3),
                    "remaining_inventory": round(new_inventory, 3),
                    "cost_per_unit": MATERIALS[mat_name]["cost_per_unit"],
                    "unit": MATERIALS[mat_name]["unit"],
                },
            ))

        self._cells_since_last_batch = 0

    def _maybe_perform_maintenance(self) -> None:
        """
        Every MAINTENANCE_INTERVAL_TICKS, restore equipment that's degraded.
        Simulates a maintenance window. Until real control actions exist
        (Session 10), this keeps the system from grinding to a permanent halt.
        """
        self._ticks_since_last_maintenance += 1
        if self._ticks_since_last_maintenance < self.MAINTENANCE_INTERVAL_TICKS:
            return

        self._ticks_since_last_maintenance = 0
        restored = []
        for eq in self.line.all_equipment:
            if eq.health_pct < 90.0:
                eq.perform_maintenance()
                restored.append(eq.equipment_id)

        if restored:
            print(f"🔧 [SIM_TIME {self.sim_now.isoformat()}] Auto-maintenance: restored {len(restored)} machines → {restored}")
    def _maybe_snapshot_metrics(self) -> None:
        """
        Once per sim-tick (every real second), snapshot key metrics
        for the dashboard's time-series charts.
        """
        # Compute current yield
        total = self.completed_count + self.scrapped_count
        yield_pct = (100.0 * self.completed_count / total) if total > 0 else 100.0

        # Compute throughput per hour (cells_completed since last snapshot, then extrapolated)
        # Simplification: at 1 tick = 1 sim-hour, throughput per hour = cells_completed since last tick
        throughput = max(0, self.completed_count - getattr(self, "_last_snapshot_completed", 0))
        self._last_snapshot_completed = self.completed_count

        # Equipment health average
        if self.line.all_equipment:
            health_avg = sum(eq.health_pct for eq in self.line.all_equipment) / len(self.line.all_equipment)
        else:
            health_avg = 100.0

        # Compliance score average (read from store, written by THEMIS)
        framework_scores = store.get_framework_scores()
        if framework_scores:
            scores = [s.get("score_pct", 100.0) for s in framework_scores.values()]
            compliance_avg = sum(scores) / len(scores)
        else:
            compliance_avg = 100.0

        # FORGE total (read from store yield_metrics)
        yield_metrics = store.get_yield_metrics()
        forge_total = yield_metrics.get("model_predictions_total", 0)
        scrap_saved = yield_metrics.get("scrap_saved_usd", 0.0)

        store.snapshot_metrics(self.sim_now.isoformat(), {
            "yield_pct": round(yield_pct, 2),
            "throughput_per_hour": throughput,
            "scrap_saved_usd": scrap_saved,
            "equipment_health_avg": round(health_avg, 2),
            "compliance_score_avg": round(compliance_avg, 2),
            "forge_evaluated_total": forge_total,
        })
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


    def _compute_cells_per_stage(self) -> dict:
        """Count cells currently at each stage of the production line."""
        counts = {}
        for cell in self.cells_in_flight:
            stage = cell.current_stage
            counts[stage] = counts.get(stage, 0) + 1
        return counts

    def status(self) -> dict:
        """Return current factory state for the dashboard / status endpoint."""
        return {
            "running": self._running,
            "sim_now": self.sim_now.isoformat(),
            "real_started_at": self.start_time.isoformat(),
            "ticks_run": self.ticks_run,
            "cells_in_flight": len(self.cells_in_flight),
            "cells_per_stage": self._compute_cells_per_stage(),
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
