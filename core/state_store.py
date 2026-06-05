"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — State Store                                             ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Single source of truth for everything the dashboard, API, and RAG      ║
║  need to read. Agents write here; readers (dashboard, RAG) read here.   ║
║                                                                           ║
║  Design choices:                                                          ║
║    • Separate read API from write API (clarity of intent)              ║
║    • Thread-safe (simulator thread + API thread both touch this)        ║
║    • Bounded collections (audit log can't grow unbounded)              ║
║    • Implementation hidden behind methods (future PostgreSQL swap)     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import logging
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Optional

logger = logging.getLogger("hephaestus.state_store")


class StateStore:
    """
    In-memory state holding everything the system needs to expose externally.

    Agents call WRITE methods to update state.
    Dashboard, REST endpoints, and RAG engine call READ methods.

    All access is thread-safe.
    """

    # Maximum entries kept in unbounded collections — prevents memory creep.
    AUDIT_LOG_MAX = 1000
    DECISIONS_MAX = 500
    CELLS_AT_RISK_MAX = 200

    def __init__(self):
        self._lock = Lock()

        # ── Audit & decisions ───────────────────────────────────────────
        self._audit_log = deque(maxlen=self.AUDIT_LOG_MAX)
        self._decisions = deque(maxlen=self.DECISIONS_MAX)

        # ── Yield & production metrics (FORGE-owned) ────────────────────
        self._yield_metrics = {
            "cells_produced_today": 0,
            "cells_scrapped_today": 0,
            "cells_at_risk": deque(maxlen=self.CELLS_AT_RISK_MAX),
            "current_yield_pct": 100.0,
            "scrap_saved_usd": 0.0,
            "model_predictions_total": 0,
            "model_predictions_correct": 0,  # for accuracy tracking
        }

        # ── Supplier scorecards (HERMES-owned) ──────────────────────────
        # Keyed by supplier name → scorecard dict
        self._supplier_scores: dict = {}
# ── Purchase orders (HERMES-owned, v2) ───────────────────────────
        # Tracks every PO from PLACED → IN_TRANSIT → RECEIVED → CONSUMED.
        self._purchase_orders = deque(maxlen=200)
        # Material inventory levels — running stock per material name.
        # Updated by simulator (consumption) and HERMES (deliveries).
        self._material_inventory: dict = {}
        # Counter for PO IDs
        self._po_counter = 0
# ── Compliance state (THEMIS-owned, v2) ───────────────────────────
        # Active findings — open compliance issues. Each has id/framework/rule/severity/status.
        self._findings = deque(maxlen=500)
        # Historical findings (closed) — for trend analysis.
        self._findings_closed = deque(maxlen=500)
        # Framework compliance scores: { framework_id: {score, open_findings, last_updated} }
        self._framework_scores: dict = {}
        # Finding ID counter
        self._finding_counter = 0
# ── Time-series history (v2 dashboard) ─────────────────────────
        # Ring buffers for key metrics. One entry per snapshot tick.
        # At ~1 snapshot/sim-hour and 24h window, we hold 24 entries.
        # But we keep a bigger buffer to allow zoom-out views.
        self._history_yield = deque(maxlen=500)
        self._history_throughput = deque(maxlen=500)
        self._history_scrap_saved = deque(maxlen=500)
        self._history_equipment_health = deque(maxlen=500)
        self._history_compliance_score = deque(maxlen=500)
        self._history_forge_evaluated = deque(maxlen=500)

        # ── Equipment state (FORGE-owned, future predictive maintenance) ─
        # Keyed by equipment_id → health dict
        self._equipment_health: dict = {}

        # ── Agent statuses ──────────────────────────────────────────────
        # Keyed by agent name → status dict
        self._agent_statuses: dict = {}

        # ── Session metadata ────────────────────────────────────────────
        self._session_id = self._make_session_id()
        self._started_at = datetime.now().isoformat()

        logger.info(f"StateStore initialized — session {self._session_id}")

    @staticmethod
    def _make_session_id() -> str:
        import uuid
        return str(uuid.uuid4())[:8].upper()

    # ════════════════════════════════════════════════════════════════════
    # WRITE API — called by agents
    # ════════════════════════════════════════════════════════════════════

    def record_audit_entry(self, entry: dict) -> None:
        """Append an audit log entry (typically from THEMIS or any agent's log_decision)."""
        with self._lock:
            self._audit_log.append(entry)

    def record_decision(self, decision: dict) -> None:
        """Append an agent decision."""
        with self._lock:
            self._decisions.append(decision)

    def update_yield_metric(self, key: str, value) -> None:
        """Update one of the headline yield metrics (e.g. 'current_yield_pct')."""
        with self._lock:
            if key in self._yield_metrics:
                self._yield_metrics[key] = value
            else:
                logger.warning(f"Unknown yield metric key: {key}")

    def increment_yield_metric(self, key: str, amount=1) -> None:
        """Atomically increment a numeric yield metric."""
        with self._lock:
            if key in self._yield_metrics and isinstance(self._yield_metrics[key], (int, float)):
                self._yield_metrics[key] += amount
            else:
                logger.warning(f"Cannot increment yield metric '{key}'")

    def add_cell_at_risk(self, cell_info: dict) -> None:
        """Add a cell flagged by FORGE as at-risk for QC failure."""
        with self._lock:
            self._yield_metrics["cells_at_risk"].append(cell_info)

    def open_finding(self, finding: dict) -> str:
        """
        Record a new compliance finding. Returns assigned finding ID.
        Required keys: framework, rule_id, severity, summary
        Optional: details (dict), source_event_id
        """
        with self._lock:
            self._finding_counter += 1
            finding_id = f"FIND-{self._finding_counter:05d}"
            finding["finding_id"] = finding_id
            finding["status"] = "OPEN"
            finding["opened_at"] = datetime.now().isoformat()
            self._findings.append(finding)
        return finding_id

    def close_finding(self, finding_id: str, resolution: str = "auto-resolved") -> bool:
        """Mark a finding as closed and move it to history."""
        with self._lock:
            target = None
            remaining = []
            for f in self._findings:
                if f.get("finding_id") == finding_id and f.get("status") == "OPEN":
                    target = f
                else:
                    remaining.append(f)
            if target is None:
                return False
            target["status"] = "CLOSED"
            target["closed_at"] = datetime.now().isoformat()
            target["resolution"] = resolution
            # Replace deque contents
            self._findings.clear()
            for f in remaining:
                self._findings.append(f)
            self._findings_closed.append(target)
        return True

    def snapshot_metrics(self, sim_time_iso: str, snapshot: dict) -> None:
        """
        Record a point-in-time snapshot for trend charts.
        Snapshot can include: yield_pct, throughput_per_hour, scrap_saved_usd,
        equipment_health_avg, compliance_score_avg, forge_evaluated_total.
        """
        with self._lock:
            ts = sim_time_iso
            if "yield_pct" in snapshot:
                self._history_yield.append({"t": ts, "v": snapshot["yield_pct"]})
            if "throughput_per_hour" in snapshot:
                self._history_throughput.append({"t": ts, "v": snapshot["throughput_per_hour"]})
            if "scrap_saved_usd" in snapshot:
                self._history_scrap_saved.append({"t": ts, "v": snapshot["scrap_saved_usd"]})
            if "equipment_health_avg" in snapshot:
                self._history_equipment_health.append({"t": ts, "v": snapshot["equipment_health_avg"]})
            if "compliance_score_avg" in snapshot:
                self._history_compliance_score.append({"t": ts, "v": snapshot["compliance_score_avg"]})
            if "forge_evaluated_total" in snapshot:
                self._history_forge_evaluated.append({"t": ts, "v": snapshot["forge_evaluated_total"]})
    def update_framework_score(self, framework_id: str, score_data: dict) -> None:
        """Update compliance score for a framework."""
        with self._lock:
            score_data["last_updated"] = datetime.now().isoformat()
            self._framework_scores[framework_id] = score_data

    def record_purchase_order(self, po: dict) -> str:
        """Add a new PO to the queue. Returns assigned PO ID."""
        with self._lock:
            self._po_counter += 1
            po_id = f"PO-{self._po_counter:05d}"
            po["po_id"] = po_id
            po["status"] = po.get("status", "PLACED")
            po["created_at"] = datetime.now().isoformat()
            self._purchase_orders.append(po)
        return po_id

    def update_purchase_order(self, po_id: str, updates: dict) -> bool:
        """Update an existing PO (status, timestamps, actual_quality, etc.)."""
        with self._lock:
            for po in self._purchase_orders:
                if po.get("po_id") == po_id:
                    po.update(updates)
                    po["last_updated"] = datetime.now().isoformat()
                    return True
        return False

    def adjust_material_inventory(self, material: str, delta: float) -> float:
        """
        Increase (positive delta) or decrease (negative delta) material inventory.
        Returns the new level.
        """
        with self._lock:
            current = self._material_inventory.get(material, 0.0)
            new_level = max(0.0, current + delta)
            self._material_inventory[material] = new_level
            return new_level

    def set_material_inventory(self, material: str, level: float) -> None:
        """Force-set inventory level for a material (used at boot)."""
        with self._lock:
            self._material_inventory[material] = max(0.0, level)

    def update_supplier_score(self, supplier: str, scorecard: dict) -> None:
        """Update a supplier's scorecard (HERMES-owned). Merges into existing,
        preserving baseline fields (quality_mean, quality_stddev, is_preferred)
        even when only observed fields are passed in."""
        with self._lock:
            existing = self._supplier_scores.get(supplier, {})
            self._supplier_scores[supplier] = {
                **existing,
                **scorecard,
                "last_updated": datetime.now().isoformat(),
            }

    def update_equipment_health(self, equipment_id: str, health: dict) -> None:
        """Set or update equipment health record."""
        with self._lock:
            self._equipment_health[equipment_id] = {
                **health,
                "last_updated": datetime.now().isoformat(),
            }

    def update_agent_status(self, agent_name: str, status: dict) -> None:
        """Refresh an agent's published status (called by agent_base)."""
        with self._lock:
            self._agent_statuses[agent_name] = status

    # ════════════════════════════════════════════════════════════════════
    # READ API — called by dashboard, REST endpoints, RAG engine
    # ════════════════════════════════════════════════════════════════════

    def get_session_info(self) -> dict:
        with self._lock:
            return {
                "session_id": self._session_id,
                "started_at": self._started_at,
                "uptime_seconds": (datetime.now() - datetime.fromisoformat(self._started_at)).total_seconds(),
            }

    def get_yield_metrics(self) -> dict:
        """Return a snapshot of the headline yield metrics."""
        with self._lock:
            cells_at_risk_list = list(self._yield_metrics["cells_at_risk"])
            return {
                "cells_produced_today": self._yield_metrics["cells_produced_today"],
                "cells_scrapped_today": self._yield_metrics["cells_scrapped_today"],
                "cells_at_risk_count": len(cells_at_risk_list),
                "cells_at_risk": cells_at_risk_list[-20:],  # last 20 only for dashboard
                "current_yield_pct": self._yield_metrics["current_yield_pct"],
                "scrap_saved_usd": self._yield_metrics["scrap_saved_usd"],
                "model_predictions_total": self._yield_metrics["model_predictions_total"],
                "model_predictions_correct": self._yield_metrics["model_predictions_correct"],
                "model_accuracy_pct": (
                    100.0 * self._yield_metrics["model_predictions_correct"]
                    / max(self._yield_metrics["model_predictions_total"], 1)
                ),
            }

    def get_findings(self, status_filter: str = "OPEN", framework_filter: str = None, limit: int = 100) -> list:
        """
        Return findings. Default returns OPEN ones, newest first.
        Pass status_filter='ALL' to get all (open + closed) in one list.
        """
        with self._lock:
            if status_filter == "ALL":
                items = list(self._findings) + list(self._findings_closed)
            elif status_filter == "CLOSED":
                items = list(self._findings_closed)
            else:
                items = [f for f in self._findings if f.get("status") == "OPEN"]
        if framework_filter:
            items = [f for f in items if f.get("framework") == framework_filter]
        return list(reversed(items))[:limit]

    def get_history(self, metric: str, last_n: int = 100) -> list:
        """
        Return time-series data for a given metric.
        Metric names: yield, throughput, scrap_saved, equipment_health, compliance_score, forge_evaluated
        """
        mapping = {
            "yield":             self._history_yield,
            "throughput":        self._history_throughput,
            "scrap_saved":       self._history_scrap_saved,
            "equipment_health":  self._history_equipment_health,
            "compliance_score":  self._history_compliance_score,
            "forge_evaluated":   self._history_forge_evaluated,
        }
        with self._lock:
            buf = mapping.get(metric)
            if buf is None:
                return []
            return list(buf)[-last_n:]
    def get_framework_scores(self) -> dict:
        """Return current compliance scores per framework."""
        with self._lock:
            return dict(self._framework_scores)

    def get_compliance_summary(self) -> dict:
        """Aggregated compliance state for dashboard."""
        with self._lock:
            open_findings = [f for f in self._findings if f.get("status") == "OPEN"]
            closed_count = len(self._findings_closed)
            scores = dict(self._framework_scores)

        by_severity = {}
        by_framework = {}
        for f in open_findings:
            sev = f.get("severity", "UNKNOWN")
            fw = f.get("framework", "UNKNOWN")
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_framework[fw] = by_framework.get(fw, 0) + 1

        return {
            "open_findings_count": len(open_findings),
            "closed_findings_count": closed_count,
            "by_severity": by_severity,
            "by_framework": by_framework,
            "framework_scores": scores,
        }
    def get_purchase_orders(self, status_filter: str = None, limit: int = 50) -> list:
        """
        Return purchase orders, optionally filtered by status.
        Newest first.
        """
        with self._lock:
            pos = list(self._purchase_orders)
        if status_filter:
            pos = [p for p in pos if p.get("status") == status_filter]
        return list(reversed(pos))[:limit]

    def get_material_inventory(self) -> dict:
        """Return snapshot of material inventory levels."""
        with self._lock:
            return dict(self._material_inventory)

    def get_procurement_summary(self) -> dict:
        """Aggregated procurement state — for dashboard / status API."""
        with self._lock:
            pos = list(self._purchase_orders)
            inventory = dict(self._material_inventory)

        by_status = {}
        total_open_value = 0.0
        for po in pos:
            status = po.get("status", "UNKNOWN")
            by_status[status] = by_status.get(status, 0) + 1
            if status in ("PLACED", "IN_TRANSIT"):
                total_open_value += po.get("total_cost_usd", 0.0)

        return {
            "total_orders": len(pos),
            "by_status": by_status,
            "open_order_value_usd": round(total_open_value, 2),
            "inventory_materials": len(inventory),
            "inventory_snapshot": inventory,
        }    
    def get_supplier_scores(self) -> dict:
        with self._lock:
            return dict(self._supplier_scores)

    def get_equipment_health(self) -> dict:
        with self._lock:
            return dict(self._equipment_health)

    def get_agent_statuses(self) -> dict:
        with self._lock:
            return dict(self._agent_statuses)

    def get_audit_log(self, limit: int = 50) -> list:
        """Return the most recent N audit entries (newest last)."""
        with self._lock:
            entries = list(self._audit_log)
        return entries[-limit:]

    def get_decisions(self, limit: int = 50) -> list:
        """Return the most recent N agent decisions."""
        with self._lock:
            decisions = list(self._decisions)
        return decisions[-limit:]

    def get_full_snapshot(self) -> dict:
        """One-shot snapshot for the dashboard / debugging."""
        return {
            "session": self.get_session_info(),
            "yield": self.get_yield_metrics(),
            "suppliers": self.get_supplier_scores(),
            "equipment": self.get_equipment_health(),
            "agents": self.get_agent_statuses(),
            "recent_audit": self.get_audit_log(limit=20),
            "recent_decisions": self.get_decisions(limit=20),
        }


# ─────────────────────────────────────────────────────────────────────────
# Module-level singleton — one shared store for the whole application.
# ─────────────────────────────────────────────────────────────────────────
store = StateStore()
