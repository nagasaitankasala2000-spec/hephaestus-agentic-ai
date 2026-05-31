"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — Compliance Framework Definitions                        ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Three real compliance frameworks that EV battery gigafactories track:  ║
║    • UN 38.3        — Battery transport safety (UN Manual of Tests)     ║
║    • IATF 16949     — Automotive quality management                      ║
║    • ISO 14001      — Environmental management                          ║
║                                                                           ║
║  Each rule maps to a specific event/condition that THEMIS evaluates.    ║
║  Severity: OBSERVATION < NEAR_MISS < FINDING < MAJOR_FINDING            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

# ════════════════════════════════════════════════════════════════════════
# FRAMEWORK METADATA
# ════════════════════════════════════════════════════════════════════════

FRAMEWORKS = {
    "UN_38_3": {
        "name": "UN 38.3",
        "full_name": "UN Manual of Tests and Criteria, Part III, Section 38.3",
        "scope": "Lithium battery transport safety",
        "version": "Rev. 7",
        "regulator": "United Nations Sub-Committee of Experts on the Transport of Dangerous Goods",
    },
    "IATF_16949": {
        "name": "IATF 16949:2016",
        "full_name": "Automotive Quality Management Systems",
        "scope": "Quality management for automotive supply chain",
        "version": "2016",
        "regulator": "International Automotive Task Force",
    },
    "ISO_14001": {
        "name": "ISO 14001:2015",
        "full_name": "Environmental Management Systems",
        "scope": "Environmental impact and sustainability",
        "version": "2015",
        "regulator": "International Organization for Standardization",
    },
}


# ════════════════════════════════════════════════════════════════════════
# COMPLIANCE RULES
# ════════════════════════════════════════════════════════════════════════
# Each rule has:
#   id                 — unique identifier (e.g., "UN383_T1")
#   framework          — which framework it belongs to
#   clause             — the clause reference (for traceability)
#   description        — human-readable summary
#   severity           — OBSERVATION / NEAR_MISS / FINDING / MAJOR_FINDING
#   trigger_event      — which event type triggers evaluation
#   evaluator          — function name in themis.py that evaluates the rule
#
# ════════════════════════════════════════════════════════════════════════

RULES = [
    # ─── UN 38.3: Battery transport safety ──────────────────────────────
    {
        "id": "UN383_T1",
        "framework": "UN_38_3",
        "clause": "38.3.4.1 — Altitude simulation",
        "description": "Cells must maintain integrity at low pressure equivalent to 15,000m altitude.",
        "severity": "OBSERVATION",
        "trigger_event": "CellLifecycleEvent",
        "evaluator": "eval_un383_altitude",
    },
    {
        "id": "UN383_T3",
        "framework": "UN_38_3",
        "clause": "38.3.4.3 — Vibration testing",
        "description": "Cells must withstand vibration profile per UN testing requirements.",
        "severity": "OBSERVATION",
        "trigger_event": "CellLifecycleEvent",
        "evaluator": "eval_un383_vibration",
    },
    {
        "id": "UN383_T7",
        "framework": "UN_38_3",
        "clause": "38.3.4.7 — Overcharge protection",
        "description": "Cells exiting Formation must show safe overcharge behavior (no thermal runaway).",
        "severity": "FINDING",
        "trigger_event": "CellLifecycleEvent",
        "evaluator": "eval_un383_overcharge",
    },
    {
        "id": "UN383_QC",
        "framework": "UN_38_3",
        "clause": "38.3.5 — Quality assurance",
        "description": "QC failure rate must remain below 2% for transport certification.",
        "severity": "FINDING",
        "trigger_event": "CellLifecycleEvent",
        "evaluator": "eval_un383_qc_rate",
    },

    # ─── IATF 16949: Automotive quality ─────────────────────────────────
    {
        "id": "IATF_8_3",
        "framework": "IATF_16949",
        "clause": "8.3 — Design and development",
        "description": "All cells must follow approved design specifications. Out-of-spec cells flagged.",
        "severity": "NEAR_MISS",
        "trigger_event": "CellLifecycleEvent",
        "evaluator": "eval_iatf_design_spec",
    },
    {
        "id": "IATF_8_4",
        "framework": "IATF_16949",
        "clause": "8.4 — Supplier control",
        "description": "Supplier quality variance must remain below 0.5% (3 sigma).",
        "severity": "NEAR_MISS",
        "trigger_event": "MaterialQualityEvent",
        "evaluator": "eval_iatf_supplier_quality",
    },
    {
        "id": "IATF_8_5",
        "framework": "IATF_16949",
        "clause": "8.5 — Production control",
        "description": "Equipment must operate within nominal health bands. Critical equipment flagged.",
        "severity": "FINDING",
        "trigger_event": "EquipmentHealthEvent",
        "evaluator": "eval_iatf_equipment_health",
    },
    {
        "id": "IATF_9_1",
        "framework": "IATF_16949",
        "clause": "9.1 — Monitoring and measurement",
        "description": "Predictive QC (FORGE) must maintain accuracy above 90%.",
        "severity": "OBSERVATION",
        "trigger_event": "CellLifecycleEvent",
        "evaluator": "eval_iatf_predictive_qc",
    },
    {
        "id": "IATF_10_2",
        "framework": "IATF_16949",
        "clause": "10.2 — Nonconformity and corrective action",
        "description": "Sustained high scrap rate triggers corrective action requirement.",
        "severity": "FINDING",
        "trigger_event": "CellLifecycleEvent",
        "evaluator": "eval_iatf_scrap_rate",
    },

    # ─── ISO 14001: Environmental ───────────────────────────────────────
    {
        "id": "ISO14_6_1",
        "framework": "ISO_14001",
        "clause": "6.1 — Environmental aspects",
        "description": "Material consumption tracked against environmental thresholds (cobalt, lithium).",
        "severity": "OBSERVATION",
        "trigger_event": "MaterialQualityEvent",
        "evaluator": "eval_iso14_material_consumption",
    },
    {
        "id": "ISO14_8_1",
        "framework": "ISO_14001",
        "clause": "8.1 — Operational planning and control",
        "description": "Conflict minerals: cobalt/lithium suppliers must hold valid certification (3TG).",
        "severity": "FINDING",
        "trigger_event": "MaterialQualityEvent",
        "evaluator": "eval_iso14_conflict_minerals",
    },
    {
        "id": "ISO14_9_1",
        "framework": "ISO_14001",
        "clause": "9.1 — Energy monitoring",
        "description": "Formation stage energy intensity must stay below 80 MW peak.",
        "severity": "OBSERVATION",
        "trigger_event": "EquipmentHealthEvent",
        "evaluator": "eval_iso14_energy",
    },
]


# ════════════════════════════════════════════════════════════════════════
# SEVERITY WEIGHTS (for computing framework compliance %)
# ════════════════════════════════════════════════════════════════════════
SEVERITY_WEIGHTS = {
    "OBSERVATION":     1.0,    # logged but doesn't reduce score
    "NEAR_MISS":       2.0,
    "FINDING":         5.0,
    "MAJOR_FINDING":  10.0,
}

# Conflict mineral certified suppliers (3TG = Tin, Tantalum, Tungsten, Gold; here we extend
# the concept to cobalt and lithium since they're the EV battery sensitive metals).
CONFLICT_MINERAL_CERTIFIED_SUPPLIERS = {
    # Cathode suppliers (contain cobalt and lithium)
    "Umicore Cathode (BE)",
    "POSCO Future M (KR)",
    # Yibin Chemical NOT certified — will trigger a finding when chosen
    # Anode suppliers
    "BTR New Energy (CN)",
    "Showa Denko (JP)",
    # Electrolyte
    "Capchem Tech (CN)",
    "Mitsubishi Chemical (JP)",
    # Other materials (foils, separators) — assumed certified
    "Asahi Kasei (JP)",
    "SK IE Technology (KR)",
    "Toray Industries (JP)",
    "Wieland Group (DE)",
    "Iljin Materials (KR)",
    "Furukawa Electric (JP)",
    "Hindalco Industries (IN)",
    "UACJ Corporation (JP)",
    "Granges AB (SE)",
}


# ════════════════════════════════════════════════════════════════════════
# HELPER LOOKUPS
# ════════════════════════════════════════════════════════════════════════

def get_rules_for_event(event_type_name: str) -> list:
    """Return all rules triggered by a given event type."""
    return [r for r in RULES if r["trigger_event"] == event_type_name]


def get_rules_for_framework(framework_id: str) -> list:
    """Return all rules in a given framework."""
    return [r for r in RULES if r["framework"] == framework_id]
