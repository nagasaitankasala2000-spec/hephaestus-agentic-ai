# HEPHAESTUS

> A multi-agent AI system simulating an EV battery gigafactory. Built as a learning exercise to understand event-driven architecture, multi-agent coordination, ML integration into operational systems, and dashboard development.

**Live:** [hephaestus-agentic-ai-production.up.railway.app](https://hephaestus-agentic-ai-production.up.railway.app)
**Author:** Naga Sai Tankasala
**License:** MIT

---

## What it is

A synthetic battery gigafactory ("TLYB\'S Gigafactory") with four agents observing and acting on a live simulation:

- **Simulator** — 9-stage production line (Mixing → Coating → Calendering → Slitting → Assembly → Electrolyte Fill → Formation → Aging → Grading) running on compressed time (1 real second ≈ 1 sim hour). Equipment degrades, materials get consumed, cells move through stages, scrap happens.
- **FORGE** — XGBoost classifier (200 trees, 14 features, trained on 25,000 synthetic cells: 95.18% accuracy, 0.9214 AUC, 0.8525 recall) that scores each cell exiting the Coating stage and flags cells with failure probability ≥ 0.70 for early scrap.
- **HERMES** — Procurement agent tracking 17 suppliers across 6 materials (NCM 811 cathode, graphite anode, electrolyte, separator film, copper foil, aluminum foil). Auto-reorders when inventory drops below 30% of typical stock. Tracks per-supplier observed quality and maintains a full PO lifecycle (PLACED → IN_TRANSIT → RECEIVED → CONSUMED).
- **THEMIS** — Compliance agent monitoring 12 rules across 3 frameworks (UN 38.3 lithium battery transport safety · IATF 16949 automotive quality · ISO 14001 environmental management). Opens findings automatically when rules are violated; auto-resolves when conditions clear.

All four agents communicate through an event bus (`core/event_bus.py`) and read/write to a shared state store (`core/state_store.py`).

---

## Dashboard

Six tabs, each backed by real API endpoints:

| Tab | Shows |
|-----|-------|
| **Executive** | Yield trend, cells shipped, throughput, scrap saved, framework scores |
| **Operations** | Throughput chart, cells-by-stage, equipment health table, recent FORGE flags |
| **Production** | SCADA-style schematic of the 9-stage line with animated cells flowing through |
| **Procurement** | Open POs, lifetime spend, spend-by-material donut, inventory bars with reorder thresholds, PO history, 17-supplier scorecards |
| **Compliance** | Findings by severity & framework, framework deep-dive cards, full findings table, all 12 monitored rules |
| **FORGE** | Cells evaluated, flag rate, scrap saved, model performance metrics, agent behavior explainer, recently flagged cells |

Built with vanilla HTML/CSS/JS + Plotly. No frontend framework. Dark "hacker SCADA" terminal aesthetic.

---

## Oracle: hybrid pseudo-RAG chat

`/api/query` accepts plain-English questions and routes to one of two backends:

- **Structured handlers** (8 of them) for live state queries: yield, equipment, findings, POs, inventory, scrap, suppliers, agents
- **Keyword-retrieval knowledge base** (10 documents covering agent behavior, frameworks, architecture) with stopword filtering and whole-word matching

Every response cites which documents/handlers it pulled context from. This is *not* a vector RAG — it\'s a deliberately simple structured-query + keyword-match system. The point was to learn the pattern, not to ship production RAG.

Set `ANTHROPIC_API_KEY` to enable Claude-powered answer generation on top of the retrieved context. Without the key, responses are deterministic and rule-based.

---

## Architecture
Simulator (factory.py) │ │ publishes events ▼ Event Bus (core/event_bus.py) ─────► State Store (core/state_store.py) │ ├──► FORGE (subscribes to CellLifecycleEvent) ├──► HERMES (subscribes to MaterialQualityEvent) └──► THEMIS (subscribes to all events, evaluates 12 rules) │ └──► /api/* endpoints (FastAPI) │ └──► static/index.html (dashboard)


- 4 typed event dataclasses (`events/types.py`)
- Compressed time: `SIM_MINUTES_PER_TICK = 60`, so a tick advances the sim clock by an hour
- Material batches emit every 100 cells produced; PO lifecycle advances on sim-clock (PLACED → IN_TRANSIT = 4 sim hours, IN_TRANSIT → RECEIVED = 24 sim hours)
- Equipment auto-maintenance fires every 120 ticks (~5 sim-days)

---

## Run locally

```bash
git clone https://github.com/nagasaitankasala2000-spec/hephaestus-agentic-ai.git
cd hephaestus-agentic-ai
pip install -r requirements.txt
python app.py
open http://localhost:8000
```

API docs at `http://localhost:8000/docs`.

---

## Project structure
hephaestus-agentic-ai/ ├── app.py FastAPI server + all REST endpoints ├── agents/ │ ├── forge.py XGBoost-based at-risk cell prediction │ ├── hermes.py Procurement: 17 suppliers, full PO lifecycle │ ├── themis.py Compliance: 3 frameworks, 12 rules │ └── oracle.py Hybrid pseudo-RAG chat ├── simulator/ │ ├── factory.py 9-stage line, time progression, event emission │ ├── equipment.py Health, throughput factor, scrap multiplier │ ├── production_line.py Stage-by-stage cell advancement │ └── config.py 17 suppliers, 6 materials, stage parameters ├── compliance/ │ └── frameworks.py UN 38.3 + IATF 16949 + ISO 14001 rule definitions ├── core/ │ ├── event_bus.py Pub/sub │ └── state_store.py Thread-safe in-memory state ├── events/types.py 4 typed event dataclasses ├── docs/knowledge_base.py 10 documents + keyword retrieval for Oracle ├── ml/ │ ├── yield_predictor.py XGBoost model wrapper │ ├── train_yield_model.py Training script │ └── models/yield_model.pkl Trained classifier (~670 KB) ├── static/index.html Dashboard (6 tabs, ~3000 lines) ├── BUGS.md Known bugs (open + closed) ├── railway.toml Railway deployment config └── requirements.txt


---

## Honest notes on what works and what doesn\'t

**Works:**
- All 6 dashboard tabs render real data from the live simulator
- FORGE evaluates every cell exiting Coating in <2ms
- HERMES PO lifecycle cycles correctly (validated by 5-hour wall-clock soak: 444 POs placed and received, all materials replenished, ELECTROLYTE correctly identified as bottleneck material)
- THEMIS auto-opens and auto-resolves findings as rule conditions change
- Oracle answers structured queries with cited sources

**Known gaps (see BUGS.md):**
- Dashboard is read-only — no buttons to trigger maintenance, resolve findings, override thresholds, or manually place POs
- Inventory can theoretically go below zero (the simulator doesn\'t halt MIXING when materials are out)
- Cells flagged by FORGE rarely trigger because the synthetic measurement variance keeps failure probability well below the 0.70 threshold

**What this is not:**
- Not a production system
- Not a real RAG (no embeddings, no vector store — keyword + structured handlers only)
- Not a benchmark or industry comparison — the simulation generates its own ground truth
- Not connected to a real ERP, MES, or factory

---

## What this project taught me

- Event-driven architecture with a pub/sub bus and shared state store
- Multi-agent coordination without tight coupling
- Integrating ML inference (XGBoost) into a running operational system
- Building a SCADA-style operations dashboard from scratch with Plotly
- The difference between wall-clock and sim-clock time, and how that distinction breaks things if you confuse the two (a real bug that took a systematic debugging session to find — documented in BUGS.md)
- Patcher-script workflows for editing large HTML files programmatically
- Deploying a Python app to Railway

---

## Tech stack

Python 3.10 · FastAPI · Uvicorn · pandas · NumPy · scikit-learn · XGBoost · Plotly (CDN) · vanilla HTML/CSS/JS · Railway

---

## Author

**Naga Sai Tankasala**
MS IT Project Management (Indiana Wesleyan, in progress) · MS Business Analytics (Sacred Heart University) · B.Tech Mechanical Engineering

Connecticut, USA

[GitHub](https://github.com/nagasaitankasala2000-spec) · [LinkedIn](https://www.linkedin.com/)

---

## License

MIT.
