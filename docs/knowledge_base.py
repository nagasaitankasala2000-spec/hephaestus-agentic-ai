"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — Knowledge Base (for pseudo-RAG)                         ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Document store used by oracle.py for keyword-based retrieval.           ║
║  Documents are auto-derived from system config where possible so they    ║
║  stay in sync with reality.                                              ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from compliance.frameworks import FRAMEWORKS, RULES


def _build_framework_docs() -> list[dict]:
    """Auto-generate one document per framework + one per rule."""
    docs = []
    for fid, fw in FRAMEWORKS.items():
        framework_rules = [r for r in RULES if r["framework"] == fid]
        rule_text = "\n".join(
            f"  • {r['id']} ({r['clause']}): {r['description']} [{r['severity']}]"
            for r in framework_rules
        )
        docs.append({
            "id": f"framework_{fid.lower()}",
            "title": fw["name"],
            "category": "compliance",
            "keywords": [
                fw["name"].lower(),
                fid.lower(),
                "compliance",
                "framework",
                "regulation",
                "standard",
                fw["scope"].lower(),
            ],
            "content": (
                f"{fw['full_name']}\n\n"
                f"Scope: {fw['scope']}\n"
                f"Version: {fw['version']}\n"
                f"Regulator: {fw['regulator']}\n\n"
                f"This framework includes {len(framework_rules)} rules that THEMIS "
                f"actively monitors:\n\n{rule_text}"
            ),
        })
    return docs


KNOWLEDGE_BASE = [
    # ──────────────────────────────────────────────────────
    # SYSTEM OVERVIEW
    # ──────────────────────────────────────────────────────
    {
        "id": "system_overview",
        "title": "HEPHAESTUS Overview",
        "category": "system",
        "keywords": ["hephaestus", "system", "overview", "what is", "architecture", "agents"],
        "content": (
            "HEPHAESTUS is a multi-agent AI system that monitors a simulated EV battery "
            "gigafactory (TLYBS) in real time. The system has 4 components running together:\n\n"
            "1. SIMULATOR — runs a continuous TLYBS Gigafactory simulation. Cells flow through "
            "9 production stages. Equipment degrades realistically. Materials get consumed. "
            "Events publish to a shared bus.\n\n"
            "2. FORGE — the yield prediction agent. Watches every cell exiting the COATING stage. "
            "Uses an XGBoost model (95% accuracy, 0.92 AUC) to predict QC failure probability. "
            "Flags high-risk cells for early scrap, saving ~$45 per saved cell.\n\n"
            "3. HERMES — the procurement intelligence agent. Tracks 17 suppliers across 6 materials. "
            "Scores them by rolling quality variance. Auto-orders when inventory drops below 30%. "
            "Picks the best-scoring supplier for each PO.\n\n"
            "4. THEMIS — the compliance + audit agent. Subscribes to all events. Evaluates against "
            "12 rules across 3 frameworks (UN 38.3, IATF 16949, ISO 14001). Opens findings when "
            "rules trigger. Auto-resolves when conditions clear."
        ),
    },

    # ──────────────────────────────────────────────────────
    # TLYBS FACTORY
    # ──────────────────────────────────────────────────────
    {
        "id": "tlybs_factory",
        "title": "TLYBS Gigafactory",
        "category": "operations",
        "keywords": ["tlybs", "gigafactory", "factory", "nevada", "4680", "battery", "production"],
        "content": (
            "TLYBS Gigafactory is a fictional EV battery production facility in Nevada, modeled "
            "as half the scale of Tesla's Gigafactory Nevada. Production target: ~18 GWh/year, "
            "~95,000 cells/day, 4680 format with NCM 811 cathode chemistry.\n\n"
            "9-stage production line:\n"
            "1. MIXING — slurry preparation, ~3 hours, MIXER-01\n"
            "2. COATING — slot die coating + drying, ~2 hours, COATER-01\n"
            "3. CALENDERING — roller compression, ~1 hour, CALENDER-01\n"
            "4. SLITTING — cut electrode strips, ~1 hour, SLITTER-01\n"
            "5. ASSEMBLY — jelly roll winding, ~2 hours, WINDER-01 + WINDER-02\n"
            "6. ELECTROLYTE_FILL — vacuum fill, ~1 hour, FILL-STATION-01\n"
            "7. FORMATION — cycling 12-18 hours at 80MW (the bottleneck), FORMATION-RACK\n"
            "8. AGING — 10-21 day temperature-controlled storage\n"
            "9. GRADING — final test + sort into A/B/C bins, GRADER-01"
        ),
    },

    # ──────────────────────────────────────────────────────
    # FORGE AGENT
    # ──────────────────────────────────────────────────────
    {
        "id": "forge_agent",
        "title": "FORGE Agent",
        "category": "agents",
        "keywords": ["forge", "yield", "prediction", "ml", "xgboost", "scrap", "model", "ai", "risk"],
        "content": (
            "FORGE is the yield prediction agent. Its job: predict cell QC failures BEFORE they "
            "consume expensive downstream resources (Formation rack time is the main bottleneck).\n\n"
            "How it works:\n"
            "• Subscribes to CellLifecycleEvent\n"
            "• Only acts on cells EXITING the COATING stage (earliest meaningful prediction point)\n"
            "• Pulls 14 features from coating-exit measurements\n"
            "• Runs them through an XGBoost classifier (200 trees, max depth 6)\n"
            "• If failure probability exceeds 0.70, flags the cell as at-risk\n"
            "• Each flag saves ~$45 (materials + labor + 18 formation hours)\n\n"
            "Model performance: 95.18% accuracy, 0.9214 AUC, 0.8525 recall, 0.9167 precision, "
            "0.8834 F1. Trained on 25,000 synthetic cells grounded in published battery physics. "
            "Production latency: ~2ms per prediction (in-process XGBoost)."
        ),
    },

    # ──────────────────────────────────────────────────────
    # HERMES AGENT
    # ──────────────────────────────────────────────────────
    {
        "id": "hermes_agent",
        "title": "HERMES Agent",
        "category": "agents",
        "keywords": ["hermes", "procurement", "supplier", "purchase", "order", "po", "material", "inventory", "reorder"],
        "content": (
            "HERMES is the procurement intelligence agent. Tracks 17 suppliers across 6 materials.\n\n"
            "Materials tracked:\n"
            "• NCM 811 cathode powder — Yibin Chemical (CN), Umicore (BE), POSCO Future M (KR)\n"
            "• Graphite anode — BTR New Energy (CN), Showa Denko (JP)\n"
            "• Electrolyte — Capchem Tech (CN), Mitsubishi Chemical (JP)\n"
            "• Separator film — Asahi Kasei (JP), SK IE (KR), Toray (JP)\n"
            "• Copper foil — Wieland (DE), Iljin Materials (KR), Furukawa Electric (JP)\n"
            "• Aluminum foil — Hindalco (IN), UACJ (JP), Granges (SE)\n\n"
            "How it works:\n"
            "• Subscribes to MaterialQualityEvent (every batch of 100 cells consumed)\n"
            "• Maintains rolling 10-lot quality scorecards per supplier\n"
            "• Auto-orders when inventory drops below 30% of typical stock\n"
            "• Picks the best-scoring supplier for each new PO\n"
            "• Tracks PO lifecycle: PLACED → IN_TRANSIT (4h) → RECEIVED (24h more)"
        ),
    },

    # ──────────────────────────────────────────────────────
    # THEMIS AGENT
    # ──────────────────────────────────────────────────────
    {
        "id": "themis_agent",
        "title": "THEMIS Agent",
        "category": "agents",
        "keywords": ["themis", "compliance", "audit", "finding", "framework", "violation", "rule", "regulation"],
        "content": (
            "THEMIS is the compliance and audit intelligence agent. Evaluates 12 rules across "
            "3 compliance frameworks in real time.\n\n"
            "Frameworks monitored:\n"
            "• UN 38.3 — Lithium battery transport safety (4 rules)\n"
            "• IATF 16949:2016 — Automotive quality management (5 rules)\n"
            "• ISO 14001:2015 — Environmental management (3 rules)\n\n"
            "How it works:\n"
            "• Subscribes to all events (cell, material, equipment, telemetry)\n"
            "• Each event evaluated against applicable rules\n"
            "• When a rule triggers: opens a finding with severity (OBSERVATION/NEAR_MISS/FINDING/MAJOR_FINDING)\n"
            "• Auto-resolves findings when conditions clear\n"
            "• Maintains compliance score per framework (100% baseline, reduced by severity weights)\n"
            "• Tracks conflict mineral certification — Yibin Chemical and other non-certified "
            "suppliers trigger ISO 14001 findings when used."
        ),
    },

    # ──────────────────────────────────────────────────────
    # SIMULATOR DETAILS
    # ──────────────────────────────────────────────────────
    {
        "id": "simulator",
        "title": "Simulator",
        "category": "system",
        "keywords": ["simulator", "simulation", "tick", "sim time", "events", "bus"],
        "content": (
            "The simulator is a background thread running an event-driven cell production model. "
            "Time compression: 1 real second = 1 simulated hour. Each tick advances the sim clock "
            "by 60 minutes.\n\n"
            "Each tick:\n"
            "1. Injects new cells into MIXING (~1-2 cells per tick at full capacity)\n"
            "2. Advances every cell in flight based on stage durations\n"
            "3. Degrades equipment health based on usage\n"
            "4. Probabilistically scraps cells based on stage failure rates × equipment health\n"
            "5. Publishes events: CellLifecycleEvent, MaterialQualityEvent, EquipmentHealthEvent, TelemetryEvent\n"
            "6. Every 100 cells: emits MaterialQualityEvent for each of 6 materials\n"
            "7. Every 120 ticks (~5 sim-days): auto-maintenance restores degraded equipment\n\n"
            "Failed equipment HALTS its stage entirely — cells back up upstream, downstream starves. "
            "Degraded equipment increases scrap probability up to 8× base rate."
        ),
    },

    # ──────────────────────────────────────────────────────
    # ARCHITECTURE
    # ──────────────────────────────────────────────────────
    {
        "id": "architecture",
        "title": "Architecture",
        "category": "system",
        "keywords": ["architecture", "design", "event bus", "state store", "pub sub", "agent"],
        "content": (
            "HEPHAESTUS uses an event-driven multi-agent architecture:\n\n"
            "Event Bus (core/event_bus.py): Thread-safe pub/sub. Module singleton. Routes typed "
            "events to subscribed handlers.\n\n"
            "State Store (core/state_store.py): Thread-safe in-memory state. Bounded deques for "
            "audit log (1000 max), decisions (500 max), cells_at_risk (200 max), purchase_orders "
            "(200 max), findings (500 max each open/closed). Separate read/write API. PostgreSQL "
            "migration path designed.\n\n"
            "Agent Base (core/agent_base.py): Abstract Agent class. Auto-registers on instantiation. "
            "Each agent declares subscribes_to = [EventType1, EventType2, ...].\n\n"
            "Typed Events (events/types.py): Frozen dataclasses with auto-generated event_id, "
            "timestamp, version. Four types: CellLifecycleEvent, TelemetryEvent, "
            "MaterialQualityEvent, EquipmentHealthEvent.\n\n"
            "Time compression: 1 real second = 1 sim hour. In-process ML inference (XGBoost ~2ms). "
            "Single-process for now, but architecture supports horizontal scaling."
        ),
    },
] + _build_framework_docs()


def search(query: str, top_k: int = 1) -> list[dict]:
    """
    Keyword-overlap search. Returns top_k documents sorted by score.
    Score = number of query keywords that appear in document keywords or title.
    """
    STOPWORDS = {"the", "and", "for", "with", "what", "how", "why", "where",
                 "when", "who", "are", "you", "your", "our", "this", "that",
                 "these", "those", "from", "into", "have", "has", "had",
                 "can", "could", "would", "should", "will", "tell", "show",
                 "give", "explain", "describe", "about", "much", "many",
                 "any", "all", "some"}
    query_words = set(
        w.lower().strip(".,!?'\"") for w in query.split() if len(w) > 2
    )
    query_words -= STOPWORDS
    if not query_words:
        return []

    scored = []
    for doc in KNOWLEDGE_BASE:
        score = 0
        # Strong match: keyword hit
        for kw in doc["keywords"]:
            kw_words = kw.lower().split()
            for w in kw_words:
                if w in query_words:
                    score += 2
        # Weak match: title overlap
        title_words = set(w.lower().strip(".,!?") for w in doc["title"].split())
        score += len(query_words & title_words)
        # Weakest match: content WHOLE-WORD hit (not substring)
        import re as _re
        content_lower = doc["content"].lower()
        for w in query_words:
            if _re.search(r"\b" + _re.escape(w) + r"\b", content_lower):
                score += 0.5

        if score >= 1.5:
            scored.append((score, doc))

    scored.sort(key=lambda x: -x[0])
    return [doc for _, doc in scored[:top_k]]
