"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — HERMES Agent (v2: real procurement intelligence)        ║
║  ────────────────────────────────────────────────────────────────────    ║
║  The Procurement Intelligence agent.                                     ║
║                                                                           ║
║  Responsibilities:                                                        ║
║    1. Track every material lot consumed (via MaterialQualityEvent)       ║
║    2. Maintain rolling supplier scorecards (quality variance, cost)      ║
║    3. Track inventory levels per material                                ║
║    4. Proactively place purchase orders when inventory drops low         ║
║    5. Pick the best-scoring supplier for each new PO                    ║
║                                                                           ║
║  Subscribes to: MaterialQualityEvent                                     ║
║  Writes to:     state_store (POs, supplier scores, inventory)           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import logging
import random
from datetime import timedelta

from core.agent_base import Agent
from core.state_store import store
from events.types import MaterialQualityEvent
from simulator.config import MATERIALS, SUPPLIERS

logger = logging.getLogger("hephaestus.hermes")


# ════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════

# Inventory level (units of material) at which HERMES auto-orders.
# Threshold = enough material for N days of production at target throughput.
# This is how real factories manage inventory: "days of coverage".
TARGET_CELLS_PER_DAY = 48000   # TLYB\'S half-scale of Tesla GF1 (~2000 cells/hr)
TARGET_DAYS_OF_COVERAGE = 2    # always keep ~2 days of inventory minimum

# Quantity ordered per PO, expressed as "cells worth of material"
PO_SIZE_CELLS = 192000  # 4 days of production at target throughput (48k/day)

# Lifecycle timing (Alpha — fast for demo visibility)
SIM_HOURS_PLACED_TO_TRANSIT = 4
SIM_HOURS_TRANSIT_TO_RECEIVED = 24

# How many lots back HERMES looks when scoring suppliers (rolling window)
SUPPLIER_WINDOW = 10


class Hermes(Agent):
    """
    The procurement intelligence agent.

    Each MaterialQualityEvent triggers:
      1. Update the supplier's running scorecard
      2. Advance any open POs through their lifecycle
      3. Check inventory levels — auto-order if below threshold
    """

    name = "HERMES"
    subscribes_to = [MaterialQualityEvent]

    def setup(self) -> None:
        """Initialize HERMES state."""
        # Per-supplier rolling lot history: { supplier_name: [quality_pct, ...] }
        self.state["supplier_history"] = {}
        # Track total spend per material
        self.state["spend_by_material"] = {}
        # Track total POs placed
        self.state["pos_placed"] = 0
        self.state["pos_received"] = 0
        # Track simulator "now" — updated from events
        self.state["sim_now"] = None
        # Track which materials we've already auto-ordered (debounce)
        self.state["pending_reorder"] = set()

        # Initialize supplier scorecards in state store
        for material, supplier_list in SUPPLIERS.items():
            for supplier in supplier_list:
                store.update_supplier_score(supplier["name"], {
                    "material": material,
                    "quality_mean": supplier["quality_mean"],
                    "quality_stddev": supplier["quality_stddev"],
                    "observed_lots": 0,
                    "observed_quality_avg": None,
                    "observed_quality_variance": None,
                    "is_preferred": False,
                })

        logger.info(f"HERMES booted — tracking {sum(len(v) for v in SUPPLIERS.values())} suppliers "
                    f"across {len(SUPPLIERS)} materials.")

    def handle(self, event: MaterialQualityEvent) -> None:
        """Process one MaterialQualityEvent."""
        # 1. Update supplier scorecard
        self._update_supplier_scorecard(event)

        # 2. Track spend
        self._track_spend(event)

        # 3. Advance PO lifecycle (using sim_now from the event)
        from datetime import datetime
        try:
            sim_iso = getattr(event, "sim_now_iso", "") or event.timestamp
            self.state["sim_now"] = datetime.fromisoformat(sim_iso)
        except Exception:
            pass
        self._advance_purchase_orders()

        # 4. Check inventory and possibly auto-order
        self._check_and_reorder(event.material)

        # 5. Publish updated status
        store.update_agent_status(self.name, self.get_status())

    # ════════════════════════════════════════════════════════════════════
    # SUPPLIER SCORING
    # ════════════════════════════════════════════════════════════════════

    def _update_supplier_scorecard(self, event: MaterialQualityEvent) -> None:
        """Update rolling quality stats for the supplier of this lot."""
        supplier_name = event.supplier
        quality_pct = event.quality_metrics.get("purity_pct", 0.0)

        # Rolling history (last N lots)
        hist = self.state["supplier_history"].setdefault(supplier_name, [])
        hist.append(quality_pct)
        if len(hist) > SUPPLIER_WINDOW:
            hist.pop(0)

        # Compute rolling stats
        avg = sum(hist) / len(hist)
        variance = sum((q - avg) ** 2 for q in hist) / len(hist)

        # Push to state store
        store.update_supplier_score(supplier_name, {
            "material": event.material,
            "observed_lots": len(hist),
            "observed_quality_avg": round(avg, 4),
            "observed_quality_variance": round(variance, 6),
            "last_quality_pct": quality_pct,
            "last_lot_id": event.lot_id,
        })

    def _track_spend(self, event: MaterialQualityEvent) -> None:
        """Track total spend per material."""
        cost = event.quality_metrics.get("cost_per_unit", 0.0)
        qty = event.quality_metrics.get("consumed_quantity", 0.0)
        lot_value = cost * qty
        self.state["spend_by_material"][event.material] = (
            self.state["spend_by_material"].get(event.material, 0.0) + lot_value
        )

    # ════════════════════════════════════════════════════════════════════
    # PURCHASE ORDER LIFECYCLE
    # ════════════════════════════════════════════════════════════════════

    def _advance_purchase_orders(self) -> None:
        """
        Check open POs and advance them through PLACED → IN_TRANSIT → RECEIVED
        based on elapsed sim-time.
        """
        sim_now = self.state.get("sim_now")
        if sim_now is None:
            return

        from datetime import datetime
        open_pos = store.get_purchase_orders(status_filter="PLACED", limit=200) + \
                   store.get_purchase_orders(status_filter="IN_TRANSIT", limit=200)

        for po in open_pos:
            try:
                placed_at = datetime.fromisoformat(po["placed_at_sim"])
            except Exception:
                continue
            elapsed_hours = (sim_now - placed_at).total_seconds() / 3600.0

            if po["status"] == "PLACED" and elapsed_hours >= SIM_HOURS_PLACED_TO_TRANSIT:
                store.update_purchase_order(po["po_id"], {
                    "status": "IN_TRANSIT",
                    "in_transit_at_sim": sim_now.isoformat(),
                })
                self.log_decision(
                    action="PO_IN_TRANSIT",
                    rationale=f"PO {po['po_id']} ({po['material']}) now in transit from {po['supplier']}",
                )

            elif po["status"] == "IN_TRANSIT" and elapsed_hours >= SIM_HOURS_PLACED_TO_TRANSIT + SIM_HOURS_TRANSIT_TO_RECEIVED:
                # Deliver the materials — add to inventory
                qty = po.get("quantity_units", 0)
                store.adjust_material_inventory(po["material"], qty)
                store.update_purchase_order(po["po_id"], {
                    "status": "RECEIVED",
                    "received_at_sim": sim_now.isoformat(),
                })
                self.state["pos_received"] += 1
                # Remove from pending reorder set so future low-inventory triggers a new PO
                self.state["pending_reorder"].discard(po["material"])

                decision = self.log_decision(
                    action="PO_RECEIVED",
                    rationale=(f"PO {po['po_id']}: received {qty} {po['unit']} of {po['material']} "
                               f"from {po['supplier']} for ${po['total_cost_usd']:.2f}"),
                    details=po,
                )
                store.record_decision(decision)
                store.record_audit_entry(decision)

    # ════════════════════════════════════════════════════════════════════
    # AUTO-REORDER LOGIC
    # ════════════════════════════════════════════════════════════════════

    def _check_and_reorder(self, material: str) -> None:
        """
        If inventory of `material` is below threshold AND no PO is already
        pending for it, place a new PO with the best-scoring supplier.
        """
        if material in self.state["pending_reorder"]:
            return

        if material not in MATERIALS:
            return

        inventory = store.get_material_inventory().get(material, 0.0)
        # Days-of-coverage threshold: how much material we'd burn in N days at target rate
        daily_consumption = MATERIALS[material]["consumption_per_cell"] * TARGET_CELLS_PER_DAY
        threshold = daily_consumption * TARGET_DAYS_OF_COVERAGE

        if inventory >= threshold:
            return

        supplier = self._pick_best_supplier(material)
        if supplier is None:
            return

        sim_now_check = self.state.get("sim_now")
        self._place_purchase_order(material, supplier)
        return

        # Time to reorder. Pick the best supplier.
        supplier = self._pick_best_supplier(material)
        if supplier is None:
            return

        self._place_purchase_order(material, supplier)

    def _pick_best_supplier(self, material: str) -> dict:
        """
        Choose the supplier for this material with the best observed quality.
        Falls back to baseline quality_mean if we have no observed data yet.
        """
        suppliers = SUPPLIERS.get(material, [])
        if not suppliers:
            return None

        scored = []
        for supplier in suppliers:
            hist = self.state["supplier_history"].get(supplier["name"], [])
            if hist:
                # Use observed average
                score = sum(hist) / len(hist)
            else:
                # Fall back to baseline
                score = supplier["quality_mean"]
            scored.append((score, supplier))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _place_purchase_order(self, material: str, supplier: dict) -> None:
        """Place a new PO with the chosen supplier."""
        mat_info = MATERIALS[material]
        quantity_units = mat_info["consumption_per_cell"] * PO_SIZE_CELLS
        cost = mat_info["cost_per_unit"]
        total_cost = quantity_units * cost

        sim_now = self.state.get("sim_now")
        if sim_now is None:
            return

        po_id = store.record_purchase_order({
            "material":            material,
            "supplier":            supplier["name"],
            "quantity_units":      round(quantity_units, 3),
            "unit":                mat_info["unit"],
            "cost_per_unit_usd":   cost,
            "total_cost_usd":      round(total_cost, 2),
            "placed_at_sim":       sim_now.isoformat(),
            "supplier_quality_mean": supplier["quality_mean"],
            "po_size_cells":       PO_SIZE_CELLS,
        })
        self.state["pos_placed"] += 1
        self.state["pending_reorder"].add(material)

        decision = self.log_decision(
            action="PO_PLACED",
            rationale=(f"PO {po_id}: ordering {quantity_units:.1f} {mat_info['unit']} of {material} "
                       f"from {supplier['name']} for ${total_cost:.2f} "
                       f"(inventory low — auto-reorder)"),
            details={
                "po_id": po_id,
                "material": material,
                "supplier": supplier["name"],
                "quantity": quantity_units,
                "cost": total_cost,
            },
        )
        store.record_decision(decision)
        store.record_audit_entry(decision)

    # ════════════════════════════════════════════════════════════════════
    # DASHBOARD STATUS
    # ════════════════════════════════════════════════════════════════════

    def hermes_summary(self) -> dict:
        """One-shot summary for dashboard / API."""
        return {
            "agent": self.name,
            "pos_placed": self.state["pos_placed"],
            "pos_received": self.state["pos_received"],
            "pending_reorders": list(self.state["pending_reorder"]),
            "suppliers_tracked": len(self.state["supplier_history"]),
            "total_spend_usd": round(sum(self.state["spend_by_material"].values()), 2),
            "spend_by_material": {
                k: round(v, 2) for k, v in self.state["spend_by_material"].items()
            },
        }


# Module-level singleton — instantiated when imported by app.py
hermes = Hermes()
