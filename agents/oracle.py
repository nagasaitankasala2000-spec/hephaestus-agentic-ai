"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — ORACLE (hybrid query agent)                             ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Replaces v1 RAG engine. Hybrid pseudo-RAG:                              ║
║    1. Tries structured query layer first (live state from store)         ║
║    2. Falls back to knowledge base search (documents)                    ║
║    3. Returns polite "I don't know" if neither matches                   ║
║                                                                           ║
║  Each answer is tagged with its source: STRUCTURED / KNOWLEDGE / UNKNOWN ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import re
from typing import Optional

from core.state_store import store
from docs.knowledge_base import search as kb_search


# ════════════════════════════════════════════════════════════════════════
# STRUCTURED QUERY HANDLERS
# ════════════════════════════════════════════════════════════════════════
# Each handler returns either a dict {"answer": str, "intent": str, "sources": [str]}
# or None if it doesn't match the question.

def _q_yield(q: str) -> Optional[dict]:
    """Current yield questions."""
    if not re.search(r"\b(yield|quality\s+rate|pass\s+rate|qc\s+rate)\b", q, re.I):
        return None
    if not re.search(r"\b(current|now|live|today|status|what)\b", q, re.I):
        return None

    metrics = store.get_yield_metrics()
    produced = metrics.get("cells_produced_today", 0)
    scrapped = metrics.get("cells_scrapped_today", 0)
    total = produced + scrapped
    yield_pct = (100.0 * produced / total) if total > 0 else 100.0

    answer = (
        f"Current yield: {yield_pct:.1f}% "
        f"({produced:,} cells passed, {scrapped:,} scrapped today). "
        f"Target is ≥94%. "
    )
    if yield_pct < 80:
        answer += "Yield is BELOW critical threshold — investigate equipment health."
    elif yield_pct < 94:
        answer += "Yield is below target. Check FORGE flags and equipment status."
    else:
        answer += "Yield is at or above target."
    return {"answer": answer, "intent": "yield_status", "sources": ["state_store.yield_metrics"]}


def _q_purchase_orders(q: str) -> Optional[dict]:
    """Open purchase order questions."""
    if not re.search(r"\b(po|pos|purchase\s+order|order|orders|procurement)\b", q, re.I):
        return None
    if not re.search(r"\b(open|active|pending|how\s+many|status|current)\b", q, re.I):
        return None

    summary = store.get_procurement_summary()
    by_status = summary.get("by_status", {})
    open_value = summary.get("open_order_value_usd", 0)

    placed = by_status.get("PLACED", 0)
    transit = by_status.get("IN_TRANSIT", 0)
    received = by_status.get("RECEIVED", 0)
    total_open = placed + transit

    answer = (
        f"{total_open} open purchase orders: "
        f"{placed} placed (awaiting shipment), {transit} in transit. "
        f"Total open value: ${open_value:,.2f}. "
        f"{received} POs have been received and consumed."
    )
    return {"answer": answer, "intent": "procurement_status", "sources": ["state_store.purchase_orders"]}


def _q_suppliers(q: str) -> Optional[dict]:
    """Supplier questions."""
    if not re.search(r"\b(supplier|suppliers|vendor|best|worst|top|score)\b", q, re.I):
        return None

    scores = store.get_supplier_scores()
    scored = [(name, s) for name, s in scores.items() if s.get("observed_lots", 0) > 0]
    if not scored:
        return {
            "answer": "No supplier quality data yet — waiting for HERMES to observe lots.",
            "intent": "supplier_status",
            "sources": ["state_store.supplier_scores"],
        }
    scored.sort(key=lambda x: -(x[1].get("observed_quality_avg") or 0))

    top = scored[:3]
    bottom = scored[-1] if len(scored) > 1 else None

    parts = ["Top 3 suppliers by observed quality:"]
    for name, s in top:
        parts.append(f"  • {name}: {s.get('observed_quality_avg', 0):.3f}% avg ({s.get('observed_lots', 0)} lots)")
    if bottom:
        parts.append(f"Lowest scorer: {bottom[0]} at {bottom[1].get('observed_quality_avg', 0):.3f}%")
    return {"answer": "\n".join(parts), "intent": "supplier_status", "sources": ["state_store.supplier_scores"]}


def _q_inventory(q: str) -> Optional[dict]:
    """Inventory level questions."""
    if not re.search(r"\b(inventory|stock|material|materials|supply|levels?)\b", q, re.I):
        return None

    inv = store.get_material_inventory()
    if not inv:
        return {"answer": "No inventory data yet.", "intent": "inventory_status", "sources": []}
    parts = ["Current material inventory:"]
    for mat, level in inv.items():
        parts.append(f"  • {mat}: {level:.2f}")
    return {"answer": "\n".join(parts), "intent": "inventory_status", "sources": ["state_store.material_inventory"]}


def _q_compliance(q: str) -> Optional[dict]:
    """Compliance and findings questions."""
    if not re.search(r"\b(compliance|finding|findings|violation|violations|audit|framework|themis)\b", q, re.I):
        return None
    if not re.search(r"\b(open|current|how\s+many|status|state|now)\b", q, re.I):
        # Pure conceptual question — let RAG handle it
        return None

    summary = store.get_compliance_summary()
    open_count = summary.get("open_findings_count", 0)
    by_fw = summary.get("by_framework", {})
    by_sev = summary.get("by_severity", {})
    scores = summary.get("framework_scores", {})

    if open_count == 0:
        answer = "✅ No open compliance findings. All 3 frameworks at 100% compliance."
        return {"answer": answer, "intent": "compliance_status", "sources": ["state_store.findings"]}

    parts = [f"{open_count} open compliance findings:"]
    for fw_id, count in by_fw.items():
        fw_score = scores.get(fw_id, {}).get("score_pct", 100)
        parts.append(f"  • {fw_id}: {count} finding(s), score {fw_score:.1f}%")
    if by_sev:
        sev_summary = ", ".join(f"{count} {sev}" for sev, count in by_sev.items())
        parts.append(f"By severity: {sev_summary}")
    return {"answer": "\n".join(parts), "intent": "compliance_status", "sources": ["state_store.findings"]}


def _q_equipment(q: str) -> Optional[dict]:
    """Equipment health questions."""
    if not re.search(r"\b(equipment|machine|machines|health|broken|failing|maintenance|critical)\b", q, re.I):
        return None
    if not re.search(r"\b(current|status|now|how|which|what|state|live)\b", q, re.I):
        return None

    equipment_states = store.get_equipment_health()
    if not equipment_states:
        return {"answer": "No equipment data yet.", "intent": "equipment_status", "sources": []}

    nominal = []
    degraded = []
    critical = []
    for eq_id, eq in equipment_states.items():
        status = eq.get("status", "UNKNOWN")
        health = eq.get("health_pct", 0)
        line = f"{eq_id} ({health:.1f}%)"
        if status == "CRITICAL" or status == "OFFLINE":
            critical.append(line)
        elif status == "DEGRADED":
            degraded.append(line)
        else:
            nominal.append(line)

    parts = []
    if critical:
        parts.append(f"⚠️  CRITICAL ({len(critical)}): {', '.join(critical)}")
    if degraded:
        parts.append(f"DEGRADED ({len(degraded)}): {', '.join(degraded)}")
    if not critical and not degraded:
        avg = sum(e.get("health_pct", 0) for e in equipment_states.values()) / len(equipment_states)
        parts.append(f"All {len(equipment_states)} machines NOMINAL. Average health: {avg:.1f}%")
    else:
        parts.append(f"{len(nominal)} machines NOMINAL.")
    return {"answer": "\n".join(parts), "intent": "equipment_status", "sources": ["state_store.equipment_health"]}


def _q_forge_status(q: str) -> Optional[dict]:
    """FORGE prediction statistics."""
    if not re.search(r"\b(forge|prediction|predictions|flags?|flagged|at\s+risk|scrap\s+saved)\b", q, re.I):
        return None
    if not re.search(r"\b(how\s+many|status|current|live|today|so\s+far)\b", q, re.I):
        # Conceptual "what is FORGE" goes to RAG
        return None

    metrics = store.get_yield_metrics()
    evaluated = metrics.get("model_predictions_total", 0)
    flagged = metrics.get("cells_at_risk_count", 0)
    saved = metrics.get("scrap_saved_usd", 0)

    answer = (
        f"FORGE has evaluated {evaluated:,} cells, flagged {flagged} as at-risk. "
        f"Estimated scrap savings: ${saved:,.2f}."
    )
    return {"answer": answer, "intent": "forge_status", "sources": ["state_store.yield_metrics"]}


def _q_overview(q: str) -> Optional[dict]:
    """High-level overview questions."""
    if not re.search(r"\b(overview|summary|status\s+report|status\s+overview|what.s\s+happening|whats\s+happening)\b", q, re.I):
        return None

    metrics = store.get_yield_metrics()
    procurement = store.get_procurement_summary()
    compliance = store.get_compliance_summary()
    equipment = store.get_equipment_health()

    produced = metrics.get("cells_produced_today", 0)
    scrapped = metrics.get("cells_scrapped_today", 0)
    total = produced + scrapped
    yield_pct = (100.0 * produced / total) if total > 0 else 100.0

    critical_eq = sum(1 for e in equipment.values() if e.get("status") in ("CRITICAL", "OFFLINE"))
    degraded_eq = sum(1 for e in equipment.values() if e.get("status") == "DEGRADED")
    open_findings = compliance.get("open_findings_count", 0)
    open_pos = procurement.get("by_status", {})
    open_po_count = open_pos.get("PLACED", 0) + open_pos.get("IN_TRANSIT", 0)

    parts = [
        f"TLYBS Gigafactory live status:",
        f"  • Yield: {yield_pct:.1f}% ({produced:,} passed, {scrapped:,} scrapped)",
        f"  • Equipment: {len(equipment)} machines, {critical_eq} CRITICAL, {degraded_eq} DEGRADED",
        f"  • FORGE: {metrics.get('model_predictions_total', 0):,} cells evaluated, {metrics.get('cells_at_risk_count', 0)} flagged",
        f"  • Scrap saved: ${metrics.get('scrap_saved_usd', 0):,.2f}",
        f"  • HERMES: {open_po_count} open POs",
        f"  • THEMIS: {open_findings} open finding(s)",
    ]
    return {
        "answer": "\n".join(parts),
        "intent": "overview",
        "sources": ["state_store"],
    }


# Order matters — more specific handlers first
STRUCTURED_HANDLERS = [
    _q_overview,
    _q_yield,
    _q_purchase_orders,
    _q_suppliers,
    _q_inventory,
    _q_compliance,
    _q_equipment,
    _q_forge_status,
]


# ════════════════════════════════════════════════════════════════════════
# ORACLE ENTRY POINT
# ════════════════════════════════════════════════════════════════════════

def ask(question: str) -> dict:
    """
    Main entry point. Tries structured handlers first, then knowledge base.

    Returns dict with keys: answer (str), intent (str), mode (str),
    sources (list[str]).
    """
    question = (question or "").strip()
    if not question or len(question) < 3:
        return {
            "answer": "Please ask a question with at least a few words.",
            "intent": "empty",
            "mode": "UNKNOWN",
            "sources": [],
        }

    # 1. Try structured handlers
    for handler in STRUCTURED_HANDLERS:
        try:
            result = handler(question)
            if result is not None:
                return {
                    **result,
                    "mode": "STRUCTURED",
                }
        except Exception as e:
            # If a structured handler crashes, fall through to RAG silently
            continue

    # 2. Fall back to knowledge base
    docs = kb_search(question, top_k=1)
    if docs:
        doc = docs[0]
        return {
            "answer": doc["content"],
            "intent": f"knowledge_{doc['category']}",
            "mode": "KNOWLEDGE",
            "sources": [f"knowledge_base:{doc['id']}"],
        }

    # 3. Polite fallback
    return {
        "answer": (
            "I don't have a specific answer for that. I can help with: "
            "current yield, open purchase orders, supplier quality, material inventory, "
            "compliance findings, equipment health, FORGE predictions, or general "
            "questions about how HEPHAESTUS works."
        ),
        "intent": "unknown",
        "mode": "UNKNOWN",
        "sources": [],
    }
