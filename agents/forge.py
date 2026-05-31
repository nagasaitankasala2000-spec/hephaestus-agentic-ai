"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — FORGE Agent                                             ║
║  ────────────────────────────────────────────────────────────────────    ║
║  The Yield Prediction Intelligence agent.                                ║
║                                                                           ║
║  Mission: predict cell QC failures BEFORE they consume Formation rack    ║
║  time. Every cell exiting COATING gets a failure probability score from  ║
║  the XGBoost model. Cells above the risk threshold are flagged for       ║
║  early scrap, saving ~$45 + 18 hours of formation time per save.         ║
║                                                                           ║
║  Subscribes to: CellLifecycleEvent                                       ║
║  Writes to:     state_store (cells_at_risk, yield_metrics, audit)        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional

from core.agent_base import Agent
from core.state_store import store
from events.types import CellLifecycleEvent
from ml.yield_predictor import predictor

logger = logging.getLogger("hephaestus.forge")


# ════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════

# Stage to score on. Coating is the earliest stage where we have enough
# signal to make a meaningful prediction.
PREDICTION_STAGE = "COATING"

# Probability threshold for flagging a cell as at-risk.
# 0.70 = ~precision/recall balance. Tune for business need.
RISK_THRESHOLD = 0.70

# Estimated cost saved per correctly-scrapped cell.
# Materials + labor + Formation rack time sunk before scrap detection.
COST_PER_SAVED_CELL_USD = 45.0


class Forge(Agent):
    """
    The yield prediction agent.

    Each time a cell exits COATING, FORGE:
      1. Pulls the measurements from the event
      2. Asks the XGBoost model for failure probability
      3. If probability > threshold, flags the cell as at-risk
      4. Updates yield metrics + audit trail
    """

    name = "FORGE"
    subscribes_to = [CellLifecycleEvent]

    def setup(self) -> None:
        """Initialize FORGE state — verify the ML model loaded."""
        self.state["model_ready"] = predictor.is_ready()
        self.state["risk_threshold"] = RISK_THRESHOLD
        self.state["cells_evaluated"] = 0
        self.state["cells_flagged"] = 0
        self.state["estimated_savings_usd"] = 0.0

        if not self.state["model_ready"]:
            logger.warning(
                "FORGE booted but yield model is NOT loaded. "
                "Predictions will return 0.0 — train the model first."
            )
        else:
            logger.info("FORGE booted with yield model loaded and ready.")

    def handle(self, event: CellLifecycleEvent) -> None:
        """Process one CellLifecycleEvent."""
        # We only score cells AS THEY EXIT COATING.
        # `previous_stage` is the stage they just left.
        if event.previous_stage != PREDICTION_STAGE:
            return

        measurements = event.measurements or {}
        if not measurements:
            # Coating exit should always have measurements; if not, skip.
            return

        # Predict failure probability
        probability = predictor.predict(measurements)
        self.state["cells_evaluated"] += 1
        store.increment_yield_metric("model_predictions_total")

        if probability > self.state["risk_threshold"]:
            self._flag_at_risk(event, probability, measurements)

        # Always push fresh agent status to store (for dashboard / status API)
        store.update_agent_status(self.name, self.get_status())

    # ════════════════════════════════════════════════════════════════════
    # ACTION: FLAG AT-RISK CELL
    # ════════════════════════════════════════════════════════════════════

    def _flag_at_risk(
        self,
        event: CellLifecycleEvent,
        probability: float,
        measurements: dict,
    ) -> None:
        """Record an at-risk cell in the state store + audit trail."""
        self.state["cells_flagged"] += 1
        self.state["estimated_savings_usd"] += COST_PER_SAVED_CELL_USD

        risk_record = {
            "cell_id":          event.cell_id,
            "stage_exited":     event.previous_stage,
            "current_stage":    event.stage,
            "risk_score":       round(probability, 4),
            "threshold":        self.state["risk_threshold"],
            "key_measurements": self._extract_key_measurements(measurements),
            "timestamp":        event.timestamp,
        }
        store.add_cell_at_risk(risk_record)
        store.increment_yield_metric("scrap_saved_usd", COST_PER_SAVED_CELL_USD)

        decision = self.log_decision(
            action="FLAG_HIGH_RISK_CELL",
            rationale=(
                f"Cell {event.cell_id} predicted to fail QC "
                f"(probability {probability:.1%}). Recommend early scrap "
                f"to save ~$45 + 18 Formation hours."
            ),
            details=risk_record,
        )
        store.record_decision(decision)
        store.record_audit_entry(decision)

    def _extract_key_measurements(self, measurements: dict) -> dict:
        """
        Return the most informative measurements for human review.
        Used by THEMIS audits and the dashboard 'why was this flagged?' view.
        """
        key_keys = [
            "coating_thickness_um",
            "coating_uniformity_cv",
            "coating_defect_density",
        ]
        return {k: measurements.get(k) for k in key_keys if k in measurements}

    # ════════════════════════════════════════════════════════════════════
    # DASHBOARD STATUS
    # ════════════════════════════════════════════════════════════════════

    def forge_summary(self) -> dict:
        """One-shot summary for the dashboard / API."""
        flagged = self.state["cells_flagged"]
        evaluated = max(self.state["cells_evaluated"], 1)
        return {
            "agent": self.name,
            "model_ready": self.state["model_ready"],
            "risk_threshold": self.state["risk_threshold"],
            "cells_evaluated": self.state["cells_evaluated"],
            "cells_flagged_at_risk": flagged,
            "flag_rate_pct": round(100.0 * flagged / evaluated, 2),
            "estimated_savings_usd": round(self.state["estimated_savings_usd"], 2),
        }


# Module-level singleton — instantiated when imported by app.py
forge = Forge()
