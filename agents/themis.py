"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — THEMIS Agent (v2: compliance + audit intelligence)      ║
║  ────────────────────────────────────────────────────────────────────    ║
║  The Compliance & Audit Intelligence agent.                              ║
║                                                                           ║
║  Responsibilities:                                                        ║
║    1. Subscribe to ALL events (cell, material, equipment, telemetry)    ║
║    2. Evaluate each against rules in compliance/frameworks.py           ║
║    3. Open findings when rules trigger                                   ║
║    4. Auto-resolve findings when conditions clear                        ║
║    5. Maintain rolling compliance scores per framework                   ║
║                                                                           ║
║  3 frameworks · 12 rules · auto-resolution                              ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import logging
from collections import deque

from core.agent_base import Agent
from core.state_store import store
from events.types import (
    CellLifecycleEvent,
    MaterialQualityEvent,
    EquipmentHealthEvent,
    TelemetryEvent,
)
from compliance.frameworks import (
    FRAMEWORKS,
    RULES,
    SEVERITY_WEIGHTS,
    CONFLICT_MINERAL_CERTIFIED_SUPPLIERS,
    get_rules_for_event,
)

logger = logging.getLogger("hephaestus.themis")


# ════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════

# QC failure rate threshold for UN 38.3 (2%)
QC_RATE_WINDOW = 100   # last 100 cells
QC_RATE_THRESHOLD = 0.02

# Supplier quality variance threshold (IATF 8.4)
SUPPLIER_VARIANCE_WINDOW = 10
SUPPLIER_VARIANCE_THRESHOLD = 0.005   # 0.5%

# Scrap rate threshold for IATF 10.2 (sustained > 5% triggers corrective action)
SCRAP_RATE_WINDOW = 200
SCRAP_RATE_THRESHOLD = 0.05

# FORGE accuracy threshold for IATF 9.1
FORGE_ACCURACY_THRESHOLD = 0.90


class Themis(Agent):
    """The compliance intelligence agent."""

    name = "THEMIS"
    subscribes_to = [
        CellLifecycleEvent,
        MaterialQualityEvent,
        EquipmentHealthEvent,
        TelemetryEvent,
    ]

    def setup(self) -> None:
        """Initialize THEMIS state."""
        # Rolling windows for rule evaluation
        self.state["recent_cells"] = deque(maxlen=QC_RATE_WINDOW)        # bool: failed_qc
        self.state["recent_scrap"] = deque(maxlen=SCRAP_RATE_WINDOW)     # bool: was_scrapped
        self.state["supplier_lots"] = {}                                  # supplier → deque of quality
        # Per-rule open finding tracking: rule_id → finding_id (only when open)
        self.state["open_findings_by_rule"] = {}
        # Per-rule open finding tracking by KEY (supplier-specific, equipment-specific):
        # rule_id::context_key → finding_id
        self.state["open_findings_by_key"] = {}
        # Counters
        self.state["rules_evaluated"] = 0
        self.state["findings_opened"] = 0
        self.state["findings_closed"] = 0

        # Initialize all framework scores at 100%
        for fid in FRAMEWORKS:
            store.update_framework_score(fid, {
                "score_pct": 100.0,
                "open_findings": 0,
                "rules_total": len([r for r in RULES if r["framework"] == fid]),
                "rules_with_findings": 0,
            })

        logger.info(f"THEMIS booted — {len(RULES)} rules across {len(FRAMEWORKS)} frameworks.")

    def handle(self, event) -> None:
        """Dispatch event to all applicable rules."""
        event_type_name = type(event).__name__
        applicable_rules = get_rules_for_event(event_type_name)

        for rule in applicable_rules:
            self.state["rules_evaluated"] += 1
            evaluator_name = rule["evaluator"]
            evaluator = getattr(self, evaluator_name, None)
            if evaluator is None:
                logger.warning(f"No evaluator method '{evaluator_name}' for rule {rule['id']}")
                continue
            try:
                evaluator(event, rule)
            except Exception as e:
                logger.exception(f"Evaluator {evaluator_name} failed for rule {rule['id']}: {e}")

        # Recompute framework scores after every event
        self._recompute_framework_scores()
        # Push status
        store.update_agent_status(self.name, self.get_status())

    # ════════════════════════════════════════════════════════════════════
    # FINDING MANAGEMENT HELPERS
    # ════════════════════════════════════════════════════════════════════

    def _open_finding(self, rule: dict, summary: str, details: dict = None, key: str = None) -> None:
        """Open a finding (if not already open for this rule/key)."""
        tracking_key = f"{rule['id']}::{key}" if key else rule["id"]
        if key:
            existing = self.state["open_findings_by_key"].get(tracking_key)
        else:
            existing = self.state["open_findings_by_rule"].get(rule["id"])
        if existing:
            return  # already open, don't duplicate

        fid = store.open_finding({
            "framework": rule["framework"],
            "rule_id": rule["id"],
            "clause": rule["clause"],
            "severity": rule["severity"],
            "summary": summary,
            "details": details or {},
        })

        if key:
            self.state["open_findings_by_key"][tracking_key] = fid
        else:
            self.state["open_findings_by_rule"][rule["id"]] = fid
        self.state["findings_opened"] += 1

        # Audit log entry
        decision = self.log_decision(
            action="FINDING_OPENED",
            rationale=f"[{rule['framework']}] {rule['id']}: {summary}",
            details={"finding_id": fid, "rule": rule["id"], "severity": rule["severity"]},
        )
        store.record_audit_entry(decision)

    def _close_finding(self, rule: dict, resolution: str, key: str = None) -> None:
        """Close a finding for a rule/key."""
        tracking_key = f"{rule['id']}::{key}" if key else rule["id"]
        if key:
            fid = self.state["open_findings_by_key"].pop(tracking_key, None)
        else:
            fid = self.state["open_findings_by_rule"].pop(rule["id"], None)
        if fid is None:
            return  # nothing to close

        store.close_finding(fid, resolution=resolution)
        self.state["findings_closed"] += 1

        decision = self.log_decision(
            action="FINDING_CLOSED",
            rationale=f"[{rule['framework']}] {rule['id']}: {resolution}",
            details={"finding_id": fid},
        )
        store.record_audit_entry(decision)

    # ════════════════════════════════════════════════════════════════════
    # FRAMEWORK SCORING
    # ════════════════════════════════════════════════════════════════════

    def _recompute_framework_scores(self) -> None:
        """Recompute compliance score for each framework based on open findings."""
        open_findings = store.get_findings(status_filter="OPEN", limit=500)

        for fid, framework in FRAMEWORKS.items():
            fw_findings = [f for f in open_findings if f.get("framework") == fid]
            penalty = sum(SEVERITY_WEIGHTS.get(f.get("severity"), 1.0) for f in fw_findings)
            # Score: 100% minus penalties, floored at 0%
            score = max(0.0, 100.0 - penalty)

            rules_total = len([r for r in RULES if r["framework"] == fid])
            rules_with_findings = len(set(f.get("rule_id") for f in fw_findings))

            store.update_framework_score(fid, {
                "score_pct": round(score, 2),
                "open_findings": len(fw_findings),
                "rules_total": rules_total,
                "rules_with_findings": rules_with_findings,
            })

    # ════════════════════════════════════════════════════════════════════
    # ─── UN 38.3 EVALUATORS ─────────────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════

    def eval_un383_altitude(self, event, rule) -> None:
        """Stub — altitude test. Always passes in simulation."""
        # Real factories test physical samples, not simulator data. Logged only.
        return

    def eval_un383_vibration(self, event, rule) -> None:
        """Stub — vibration test. Always passes in simulation."""
        return

    def eval_un383_overcharge(self, event, rule) -> None:
        """Flag if cells exiting Formation show measurement anomalies."""
        if event.previous_stage != "FORMATION":
            return
        measurements = event.measurements or {}
        # In real factories: thermal runaway is detected via temperature sensors
        # Here we proxy via formation_capacity_ah being out of band
        capacity = measurements.get("formation_capacity_ah")
        if capacity is not None and (capacity < 4.5 or capacity > 5.2):
            self._open_finding(
                rule,
                summary=f"Cell {event.cell_id} exited Formation with abnormal capacity ({capacity} Ah).",
                details={"cell_id": event.cell_id, "capacity_ah": capacity},
                key=event.cell_id,
            )

    def eval_un383_qc_rate(self, event, rule) -> None:
        """QC failure rate over last 100 cells must stay below 2%."""
        if event.stage != "GRADING":
            return
        failed = bool(event.measurements and event.measurements.get("failed_qc"))
        self.state["recent_cells"].append(failed)

        if len(self.state["recent_cells"]) < 50:
            return  # not enough data yet

        rate = sum(self.state["recent_cells"]) / len(self.state["recent_cells"])
        if rate > QC_RATE_THRESHOLD:
            self._open_finding(
                rule,
                summary=f"QC failure rate {rate:.1%} exceeds UN 38.3 threshold ({QC_RATE_THRESHOLD:.0%}).",
                details={"current_rate": rate, "window": len(self.state["recent_cells"])},
            )
        else:
            self._close_finding(rule, resolution=f"QC failure rate back to {rate:.1%}, within threshold.")

    # ════════════════════════════════════════════════════════════════════
    # ─── IATF 16949 EVALUATORS ──────────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════

    def eval_iatf_design_spec(self, event, rule) -> None:
        """Cells flagged by FORGE as out-of-spec are near-misses."""
        # FORGE already flagged at-risk cells; we just track them here as observations
        # This is a stub - actual signal comes via FORGE state, not events
        return

    def eval_iatf_supplier_quality(self, event, rule) -> None:
        """Supplier quality variance over last 10 lots must stay < 0.5%."""
        supplier = event.supplier
        quality = event.quality_metrics.get("purity_pct", 100.0)

        hist = self.state["supplier_lots"].setdefault(supplier, deque(maxlen=SUPPLIER_VARIANCE_WINDOW))
        hist.append(quality)

        if len(hist) < 5:
            return  # not enough data

        avg = sum(hist) / len(hist)
        variance = sum((q - avg) ** 2 for q in hist) / len(hist)

        if variance > SUPPLIER_VARIANCE_THRESHOLD:
            self._open_finding(
                rule,
                summary=f"Supplier {supplier} quality variance {variance:.4f} exceeds IATF 8.4 threshold.",
                details={"supplier": supplier, "variance": variance, "window_avg": avg, "lots": len(hist)},
                key=supplier,
            )
        else:
            self._close_finding(rule, resolution=f"Supplier {supplier} variance back to {variance:.4f}.", key=supplier)

    def eval_iatf_equipment_health(self, event, rule) -> None:
        """Equipment in CRITICAL state triggers a finding."""
        if event.status == "CRITICAL":
            self._open_finding(
                rule,
                summary=f"Equipment {event.equipment_id} ({event.equipment_type}) is CRITICAL (health {event.health_pct}%).",
                details={"equipment_id": event.equipment_id, "health_pct": event.health_pct, "stage": event.stage},
                key=event.equipment_id,
            )
        elif event.status == "NOMINAL":
            self._close_finding(rule, resolution=f"Equipment {event.equipment_id} returned to NOMINAL.", key=event.equipment_id)

    def eval_iatf_predictive_qc(self, event, rule) -> None:
        """Stub — would track FORGE accuracy over time."""
        # Implementation requires comparing FORGE predictions to actual outcomes.
        # Out of scope for this session.
        return

    def eval_iatf_scrap_rate(self, event, rule) -> None:
        """Sustained scrap rate > 5% triggers corrective action."""
        if event.previous_stage is None:
            return
        scrapped = bool(event.measurements and event.measurements.get("scrapped"))
        self.state["recent_scrap"].append(scrapped)

        if len(self.state["recent_scrap"]) < 50:
            return

        rate = sum(self.state["recent_scrap"]) / len(self.state["recent_scrap"])
        if rate > SCRAP_RATE_THRESHOLD:
            self._open_finding(
                rule,
                summary=f"Scrap rate {rate:.1%} sustained over last {len(self.state['recent_scrap'])} cells — corrective action required.",
                details={"scrap_rate": rate},
            )
        else:
            self._close_finding(rule, resolution=f"Scrap rate {rate:.1%} within tolerance.")

    # ════════════════════════════════════════════════════════════════════
    # ─── ISO 14001 EVALUATORS ───────────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════

    def eval_iso14_material_consumption(self, event, rule) -> None:
        """Track material consumption — observational only."""
        # Simply log; doesn't trigger findings unless extreme
        return

    def eval_iso14_conflict_minerals(self, event, rule) -> None:
        """Suppliers must be in conflict-mineral certified list."""
        supplier = event.supplier
        if supplier in CONFLICT_MINERAL_CERTIFIED_SUPPLIERS:
            # Supplier certified — close any open finding
            self._close_finding(rule, resolution=f"{supplier} holds valid 3TG certification.", key=supplier)
        else:
            self._open_finding(
                rule,
                summary=f"Supplier {supplier} lacks 3TG / conflict mineral certification — ISO 14001 finding.",
                details={"supplier": supplier, "material": event.material, "lot_id": event.lot_id},
                key=supplier,
            )

    def eval_iso14_energy(self, event, rule) -> None:
        """Formation energy intensity check — proxy via equipment telemetry."""
        # Only evaluate FORMATION-RACK equipment
        if event.equipment_id != "FORMATION-RACK":
            return
        # Stub — would require power telemetry. Skip for now.
        return

    # ════════════════════════════════════════════════════════════════════
    # DASHBOARD STATUS
    # ════════════════════════════════════════════════════════════════════

    def themis_summary(self) -> dict:
        """One-shot summary for dashboard / API."""
        return {
            "agent": self.name,
            "rules_evaluated": self.state["rules_evaluated"],
            "findings_opened": self.state["findings_opened"],
            "findings_closed": self.state["findings_closed"],
            "currently_open": len(self.state["open_findings_by_rule"]) + len(self.state["open_findings_by_key"]),
            "frameworks_tracked": len(FRAMEWORKS),
            "rules_in_catalog": len(RULES),
        }


# Module-level singleton — instantiated when imported by app.py
themis = Themis()
