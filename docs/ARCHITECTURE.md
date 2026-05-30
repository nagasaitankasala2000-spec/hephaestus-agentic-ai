# HEPHAESTUS v2 — Architecture & Decision Record

**Status:** Approved · Ready for implementation
**Date:** May 2026
**Author:** HEPHAESTUS engineering session
**Companion document:** `TLYBS_OPERATIONS.md` (operational reference for the gigafactory being simulated)

---

## 1. EXECUTIVE SUMMARY

HEPHAESTUS v2 is the production-grade evolution of the v1 prototype. The fundamental change: instead of analyzing static Kaggle datasets when triggered by dashboard button clicks, the system now runs against a continuous simulation of TLYB'S — a fictional EV battery gigafactory modeled on Tesla Gigafactory Nevada at half-scale. Three specialized AI agents monitor every cell as it moves through the nine-stage production line, predict quality failures before they consume expensive downstream resources, score supplier quality variance in real time, and maintain a full compliance audit trail.

**Primary objective of the AI system:** maximize yield on the cell production line. At TLYB'S scale (~95,000 cells per day), every 1% yield improvement represents approximately $15-20 million in annual savings.

**One-sentence description (use this in interviews):**
HEPHAESTUS v2 is a multi-agent AI system that runs against a continuous simulation of an EV battery gigafactory, predicting cell quality failures before they consume expensive downstream resources and maintaining a full audit trail of every decision.

---

## 2. WHAT'S DIFFERENT FROM v1

| Dimension | v1 | v2 |
|---|---|---|
| Data source | Static Kaggle CSV files loaded at startup | Continuous synthetic event stream from TLYB'S simulator |
| Agent trigger | Manual dashboard button clicks | Automatic via event bus subscription |
| Agent intelligence | Rule-based scoring + lookups | Real ML model (XGBoost) for yield prediction; algorithmic scoring for procurement |
| State management | Globals updated on demand | Typed state store with read API, abstracted for future PostgreSQL swap |
| Event flow | None — direct function calls | Typed event bus with pub/sub pattern |
| Time | Static snapshot | Time-compressed continuous simulation (1 real second = 1 simulated hour) |
| Audit trail | Logged when buttons clicked | Logged for every event and every agent decision automatically |
| Dashboard | Reactive (updates after button click) | Live (polls every 2 seconds, always reflects current state) |

**What's kept from v1:** FastAPI app structure, the dashboard frontend (with additions), the RAG engine, the chat widget, the basic audit logging infrastructure, the names and roles of HERMES / FORGE / THEMIS.

---

## 3. SYSTEM ARCHITECTURE

### 3.1 High-level diagram

```
╔══════════════════════════════════════════════════════════════════════╗
║                  HEPHAESTUS v2 — SINGLE PYTHON PROCESS                ║
║                       (runs on Railway, 1GB RAM)                       ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                        ║
║  BACKGROUND THREAD:  TLYB'S Factory Simulator                         ║
║                      ↓ emits typed events                              ║
║                                                                        ║
║  EVENT BUS (in-memory pub/sub)                                         ║
║                      ↓ routes by event type                            ║
║                                                                        ║
║  AGENTS (auto-discovered from agents/ folder)                          ║
║    HERMES (procurement)  ·  FORGE (yield)  ·  THEMIS (audit)          ║
║                      ↓ write decisions and metrics                     ║
║                                                                        ║
║  STATE STORE (in-memory, abstracted for future DB swap)                ║
║                      ↓ exposes read API                                ║
║                                                                        ║
║  FastAPI Layer  ·  RAG Engine                                          ║
║                      ↓                                                 ║
╚══════════════════════════════════════════════════════════════════════╝
                       ↓
               DASHBOARD (browser, polls every 2s)
```

### 3.2 The seven components

**1. Factory Simulator** (`simulator/`)
- Runs as a background thread, started when the app boots
- Ticks every 1 real second = 1 simulated hour (demo-fast time compression)
- Maintains internal state for: cells in flight, equipment health, material inventory
- Emits typed events to the event bus

**2. Event Bus** (`core/event_bus.py`)
- In-memory pub/sub mechanism
- Agents subscribe to specific event types at boot time
- When the simulator emits an event, the bus routes it to every interested agent
- Synchronous within a process — no message queue infrastructure needed

**3. Typed Events** (`events/types.py`)
- Each event type is a Python dataclass with a `version` field
- Primary types: `TelemetryEvent`, `CellLifecycleEvent`, `MaterialQualityEvent`, `EquipmentHealthEvent`
- Versioning allows new event fields without breaking existing agents

**4. Agents** (`agents/`)
- Each agent is a Python class extending the `Agent` base class
- Declares which event types it subscribes to
- Auto-discovered at boot — drop a new file in `agents/`, it's registered automatically
- Three agents in v2: HERMES (procurement), FORGE (yield), THEMIS (audit & compliance)

**5. State Store** (`core/state_store.py`)
- In-memory single source of truth for everything the dashboard and RAG need
- Exposes a clean read API: `get_current_yield()`, `get_cells_at_risk()`, `get_supplier_scores()`, etc.
- Implementation is hidden behind the API — future swap to PostgreSQL doesn't require touching agents

**6. ML Model** (`ml/`)
- XGBoost classifier predicting cell QC failure probability
- Trained on synthetic data generated from published battery research (grounded in real physics, since real cell-level production data is proprietary)
- Loaded once at boot, called in-process by FORGE for every cell exiting the Coating stage
- Inference latency: 1-5 ms per cell (in-process — no separate ML service overhead)

**7. FastAPI + RAG + Dashboard** (existing, with additions)
- FastAPI exposes REST endpoints that read from STATE
- RAG engine sits on top of STATE for natural language queries
- Dashboard polls REST endpoints every 2 seconds

---

## 4. DATA FLOW

A typical event's life cycle:

```
1. Simulator tick (every 1 real second)
   └─> Simulator advances a cell from "COATING" to "CALENDERING" stage
   └─> Creates a CellLifecycleEvent with measurements (coating thickness, uniformity)

2. Simulator publishes event to Event Bus

3. Event Bus inspects event type → routes to interested subscribers
   ├─> FORGE (subscribes to CellLifecycleEvent + TelemetryEvent)
   └─> THEMIS (subscribes to ALL events)

4. FORGE handler:
   ├─> Extracts process measurements from event
   ├─> Calls yield_predictor.predict() → returns probability of QC failure
   ├─> If probability > 0.70 → flag cell for early scrap, write decision to STATE
   └─> Update model performance metrics in STATE

5. THEMIS handler:
   ├─> Append event to audit log in STATE
   └─> Update event counter, agent activity tracker

6. Dashboard polls /api/yield 1.8 seconds later
   └─> Endpoint reads STATE.get_current_yield()
   └─> Returns JSON with current %, scrap saved, cells at risk

7. Dashboard renders updated numbers
   └─> User sees yield ticked up by 0.02%, scrap counter incremented by $35
```

End-to-end latency from simulator event to dashboard render: approximately 2 seconds (dominated by dashboard poll interval, not by any processing step).

---

## 5. KEY ARCHITECTURAL DECISIONS

This section documents the specific decisions made during design, why each was chosen, and what alternatives were rejected.

### Decision 1: Single process, not microservices

**Choice:** Run everything (simulator + agents + ML + API + RAG) in a single Python process.

**Why:** Railway provides 1 GB RAM and 2 vCPUs — adequate for our scale. Splitting into microservices would add operational complexity (deploying multiple services, managing inter-service communication, debugging across network boundaries) without any compensating benefit at our scale.

**Rejected alternatives:**
- Microservices with message queue (Kafka/RabbitMQ): would add 4-5 sessions of build time, $25-50/mo cost, harder debugging, slower demo. Not justified.
- Serverless functions: latency penalty for cold starts kills the live-demo experience.

**Migration path if needed:** The agent registry pattern means we could extract any agent into its own service later by adding a network transport layer to the event bus. Architecture supports this without a rewrite.

---

### Decision 2: Background thread for the simulator, not asyncio

**Choice:** Run the simulator in a separate thread from FastAPI's main event loop.

**Why:** The simulator needs to run continuously, independent of HTTP requests. FastAPI by itself is request-response; it only does work when someone hits an endpoint. We need parallel execution. Threading is the simplest way to get that in Python for our I/O-light, computation-light workload.

**Rejected alternatives:**
- asyncio task: would require restructuring FastAPI startup to schedule it; threading is simpler.
- Separate worker process (Celery, RQ): adds Redis dependency, harder debugging, marginal benefit.
- Multiprocessing: real CPU parallelism we don't need; loses shared memory access to STATE.

**Known limitation:** Python's GIL prevents true CPU parallelism between the simulator thread and the API request handlers. This is fine because the simulator is I/O-light and our request rate is low. If we ever hit CPU bottlenecks, switching to multiprocessing with explicit IPC is the migration path.

---

### Decision 3: In-memory state, not a database

**Choice:** Keep all current state (cells in flight, agent decisions, audit log, model metrics) in Python objects in memory.

**Why:** Microsecond read latency makes the dashboard feel instant. Zero ops overhead (no database to provision, no migrations, no schema versioning). State naturally fits in 1 GB RAM at our scale (~95,000 cells/day with rolling cleanup of completed cells).

**Trade-off accepted:** Railway redeploys reset state. For a demo project, this is acceptable — we can re-seed the simulator on startup. For a production system, this would be unacceptable.

**Migration path:** The State Store is accessed through a clean read API. Reimplementing it on top of PostgreSQL would be a 1-day change. No agent code would need modification. This is the single highest-leverage abstraction in the architecture.

**Rejected alternatives:**
- PostgreSQL from day one: adds setup time, costs ~$5-10/mo extra on Railway, slows the dashboard. Not justified for Phase 1.
- Redis: solves the wrong problem (we don't need cross-process state).
- SQLite: gives us persistence but adds ORM complexity for no read-performance gain.

---

### Decision 4: Pluggable agent registry, not hardcoded agents

**Choice:** Auto-discover agents from the `agents/` folder at boot. Each agent declares its event subscriptions.

**Why:** Future expansion (adding SAGE for energy management, ATLAS for supply chain resilience, etc.) becomes a matter of writing new code, not refactoring old code. New agents are independent; they cannot break existing ones.

**Cost:** ~2 hours of extra design work upfront to build the registry. Saves weeks of refactoring as Phase 2/3/4 add agents.

**Rejected alternatives:**
- Hardcoded list of agents in app.py: simpler now, but every new agent requires touching `app.py`, which becomes a refactor risk over time.
- Plugin system with external configuration: over-engineered for a single repo we control.

---

### Decision 5: Typed events with versioning

**Choice:** Events are Python dataclasses with explicit fields and a `version` integer.

**Why:** Type safety catches bugs at the boundary between simulator and agents. Versioning allows us to add fields to event types in Phase 2 without breaking agents written in Phase 1.

**Cost:** ~1 hour of upfront design to define event types properly. Saves a class of bugs that would otherwise multiply as we add event types.

**Rejected alternatives:**
- Generic dictionaries (`{"type": "telemetry", "data": {...}}`): no type safety, no IDE autocomplete, every agent has to defensively parse event contents.
- Protobuf / Avro: industrial-grade schema systems we don't need at our scale; would add toolchain complexity.

---

### Decision 6: In-process ML inference, not a serving framework

**Choice:** Load the XGBoost model once at boot. Call it directly from FORGE.

**Why:** One model, predictable latency, no operational overhead. In-process inference is 1-5 ms. A separate ML service (BentoML, TorchServe) would add 50-200 ms per call, plus deployment complexity.

**Rejected alternatives:**
- BentoML / TorchServe / Triton: solves problems we don't have (multi-model serving, A/B testing, model versioning at scale).
- Cloud ML endpoint (SageMaker, Vertex AI): network latency, vendor lock-in, cost.

**Migration path if we ever serve many models:** Extract `yield_predictor.py` into a service. Other agent code unchanged because they call `yield_predictor.predict()` through a wrapper.

---

### Decision 7: Synthetic training data, grounded in published research

**Choice:** Train the yield prediction model on synthetic cell production data generated from known battery science equations, not on the Kaggle PdM dataset directly.

**Why:** The Kaggle PdM dataset is about generic industrial equipment failure, not cell production. There is no public dataset of lithium-ion cell process parameters paired with QC outcomes — that data is proprietary to manufacturers. The right approach is to generate synthetic training data using published relationships (e.g., coating thickness variance → cell capacity variance, calendering pressure → electrode density → impedance).

**Honest defense in interviews:** "The yield model is trained on synthetic data generated from published battery science literature, because real cell-level production data is proprietary to manufacturers. The architecture is production-grade and would work identically with real data if I had access through an employer."

**Cost:** We need to write a synthetic data generator (~200 lines of code in Session 4) that produces realistic distributions. This is itself a portfolio-positive artifact — it demonstrates we understand the underlying physics.

---

### Decision 8: REST API + polling, not WebSockets

**Choice:** Dashboard polls REST endpoints every 2 seconds.

**Why:** Polling is simple, debuggable, and works through every firewall and proxy. WebSockets would give us push-based real-time updates, which is technically more efficient but adds connection management complexity.

**Rejected alternatives:**
- WebSockets: would shave 1-2 seconds off update latency, but at the cost of connection state, reconnection logic, and harder debugging.
- Server-Sent Events: similar trade-off to WebSockets.

**Migration path:** If real-time becomes important, we add a WebSocket endpoint alongside the existing REST endpoints. No backward-compatibility break.

---

## 6. FILE STRUCTURE

```
hephaestus-agentic-ai/
│
├── app.py                          # FastAPI app, agent bootstrapping, event bus wiring
├── rag_engine.py                   # (existing, minor update for new state API)
├── requirements.txt                # (add: xgboost, scikit-learn)
├── railway.toml                    # (existing)
│
├── core/                           # SHARED INFRASTRUCTURE
│   ├── __init__.py
│   ├── event_bus.py                # In-memory pub/sub event router
│   ├── state_store.py              # Typed in-memory state with read API
│   └── agent_base.py               # Base class all agents extend
│
├── events/                         # TYPED EVENT DEFINITIONS
│   ├── __init__.py
│   └── types.py                    # CellLifecycleEvent, TelemetryEvent, etc.
│
├── simulator/                      # TLYB'S FACTORY SIMULATOR
│   ├── __init__.py
│   ├── factory.py                  # Main simulator loop (runs in background thread)
│   ├── production_line.py          # 9-stage cell production process model
│   ├── cell.py                     # Individual cell lifecycle object
│   ├── equipment.py                # Equipment state and health degradation
│   └── config.py                   # Time compression, line capacity, material inventories
│
├── agents/                         # PLUGGABLE AGENT REGISTRY
│   ├── __init__.py
│   ├── hermes.py                   # Procurement quality scoring agent
│   ├── forge.py                    # Yield prediction agent (wraps ML model)
│   └── themis.py                   # Audit, compliance, model performance tracking
│
├── ml/                             # MACHINE LEARNING
│   ├── __init__.py
│   ├── train_yield_model.py        # Training script (run offline once)
│   ├── synthetic_data.py           # Synthetic training data generator
│   ├── yield_predictor.py          # Inference wrapper used by FORGE
│   └── models/
│       └── yield_model.pkl         # Trained model artifact
│
├── static/
│   └── index.html                  # (existing — gets new live production line viz)
│
├── data/                           # (existing — Kaggle reference data)
│
├── docs/                           # PROJECT DOCUMENTATION
│   ├── TLYBS_OPERATIONS.md         # Operational reference for the gigafactory
│   └── ARCHITECTURE.md             # This document
│
└── README.md                       # (gets major v2 rewrite at end of build)
```

---

## 7. BUILD SEQUENCE

The build is divided into four sessions of approximately 90 minutes each, after this design session.

### Session 2 — Core infrastructure
**Deliverables:**
- `core/event_bus.py` (pub/sub mechanism)
- `core/state_store.py` (typed state with read API)
- `core/agent_base.py` (base class for agents)
- `events/types.py` (initial event type definitions)
- Refactor existing HERMES/FORGE/THEMIS to use the agent base class
- Wire agent registry into `app.py` startup

**Ship criterion:** Existing dashboard still works. Existing API endpoints still work. Agents now also auto-register with the event bus (but receive no events yet — simulator comes next session). Commit and push, deploy verifies on Railway.

### Session 3 — Factory simulator
**Deliverables:**
- `simulator/factory.py` (main loop)
- `simulator/production_line.py` (9-stage model)
- `simulator/cell.py`, `simulator/equipment.py`, `simulator/config.py`
- Simulator emits events to the bus
- `/api/simulator/status` endpoint

**Ship criterion:** Boot the app, wait 30 seconds, see events flowing through the audit log without anyone clicking anything. Dashboard shows live activity. Commit and push.

### Session 4 — ML model + FORGE upgrade
**Deliverables:**
- `ml/synthetic_data.py` (data generator)
- `ml/train_yield_model.py` (XGBoost training)
- `ml/yield_predictor.py` (inference wrapper)
- Trained `yield_model.pkl` artifact (committed to repo)
- FORGE upgraded to call the model for every cell exiting Coating
- Yield metrics added to STATE and dashboard

**Ship criterion:** Dashboard shows live yield percentage updating. "Cells at risk" list populates. Scrap savings counter ticks up. Commit and push.

### Session 5 — Dashboard polish + ship
**Deliverables:**
- Production line visualization on dashboard (cells flowing through stages)
- Yield widgets, scrap savings widget
- Updated README.md (v2 version, live URL, screenshots, performance metrics)
- Fresh screenshots
- LinkedIn post

**Ship criterion:** v2 is live, README is published, LinkedIn post is up.

---

## 8. KNOWN LIMITATIONS

Honest documentation of what v2 does NOT do, so future-us doesn't pretend otherwise:

1. **No persistence.** Railway restarts reset all state. Acceptable for a demo, not for production.
2. **No authentication.** Anyone with the URL can interact with the system. Acceptable for a portfolio piece; not for a real product.
3. **Single-machine scale.** Architecture assumes everything fits in one process. Not horizontally scalable as-is.
4. **No real factory data.** Training data is synthetic, grounded in published research. Real production data would improve the model.
5. **Simulator is closed-loop without external feedback.** The simulator's behavior isn't influenced by agent decisions — agents observe but don't intervene in the simulated reality. This is a deliberate simplification for Phase 1.
6. **One optimization target.** Phase 1 optimizes for yield only. Supply chain resilience, energy management, predictive maintenance, cross-line orchestration are not in scope.

Each limitation has a documented migration path in the corresponding architectural decision above. None is a fundamental design flaw — they are deliberate scope choices.

---

## 9. WHAT THIS ARCHITECTURE LETS US SAY IN INTERVIEWS

Three sentences, ready for use:

**To a recruiter / non-technical hiring manager:**
"HEPHAESTUS is a multi-agent AI system that runs against a continuous simulation of an EV battery gigafactory. Three specialized agents monitor every cell as it's produced, predict quality failures before they consume expensive downstream resources, and maintain a complete audit trail. It demonstrates how agentic AI can reduce scrap and improve operational efficiency in real-world manufacturing."

**To a technical hiring manager:**
"Single-process Python event-driven architecture. A factory simulator runs as a background thread, emitting typed events to an in-memory pub/sub bus. Three pluggable agents subscribe to event types they care about — HERMES for procurement quality scoring, FORGE for ML-based yield prediction wrapping an XGBoost model, THEMIS for audit and compliance. State is held in a typed in-memory store with a clean read API, deliberately abstracted to allow a future PostgreSQL swap without touching agent code. The single-process design is a Phase 1 trade-off prioritizing ship speed and debuggability over horizontal scale."

**To a senior engineer evaluating your judgment:**
"The architecture is deliberately right-sized for the scale and timeline. I considered microservices, event sourcing, and a separate ML serving framework. I rejected all of them because they would have added operational complexity without solving any problem we actually had. The architecture has two specific extensibility hooks — a pluggable agent registry and versioned typed events — so Phase 2 capabilities like supply chain resilience or energy management can be added by writing new code, not by refactoring existing code. Every decision has a documented migration path if scale changes the constraints."

---

## 10. DECISION OWNERS

For traceability — every major decision in this document was made jointly between the engineering session participant (Naga Sai Tankasala) and the AI/ML engineering consultant role played by Claude (Anthropic). Decisions are owned by the human; the consultant role was advisory.

---

*End of architecture document. Implementation begins with Session 2.*
