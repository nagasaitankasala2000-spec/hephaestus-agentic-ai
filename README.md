# Project HEPHAESTUS 🔥

### Agentic AI for Industrial Enterprise Workflows

> A multi-agent autonomous AI system designed for manufacturing and industrial operations — covering procurement automation, shop floor scheduling, compliance auditing, and a natural-language query interface. Inspired by the gap in enterprise AI: everyone builds horizontal chatbots, nobody builds deep industrial execution intelligence.

---

## 🌐 Live Demo

| Resource | Link |
|----------|------|
| **🖥️ Live Dashboard** | [hephaestus-agentic-ai-production.up.railway.app](https://hephaestus-agentic-ai-production.up.railway.app) |
| **📊 API Explorer (Swagger)** | [/docs](https://hephaestus-agentic-ai-production.up.railway.app/docs) |
| **🤖 Natural Language Query** | `POST /api/query` |
| **🔍 System Status** | [/api/status](https://hephaestus-agentic-ai-production.up.railway.app/api/status) |

> Deployed on Railway. Backed by real Kaggle manufacturing + supply chain datasets.

---

## 🖥️ Live Dashboard

![HEPHAESTUS Dashboard](https://github.com/nagasaitankasala2000-spec/hephaestus-agentic-ai/raw/main/images/hephaestus_dashboard.png)

*Three agents running simultaneously — HERMES (procurement), HEPHAESTUS CORE (shop floor), and THEMIS (compliance) — with real-time metrics, purchase order queue, machine health index, production schedule, and audit trail.*

---

## 🧠 Concept & Motivation

Every major AI vendor is racing to deploy GenAI horizontally — chatbots, copilots, content generation. The real white space?

**AI that doesn't just suggest the next step — it executes it, autonomously, inside a real industrial process, with full auditability.**

This project explores what that looks like: three specialized agents, each owning a distinct domain of industrial operations, coordinated by a central orchestrator, with every action logged in a human-readable audit trail — and a RAG layer that lets you ask the system anything in plain English.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│                  HEPHAESTUS ORCHESTRATOR                   │
│              Coordinates all agents & message bus          │
└────────┬──────────────┬──────────────┬────────────────────┘
         │              │              │
   ┌─────▼─────┐  ┌─────▼─────┐  ┌────▼──────┐
   │  HERMES   │  │ HEPHAESTUS│  │  THEMIS   │
   │Procurement│  │   CORE    │  │Compliance │
   │  Agent    │  │ Scheduling│  │  & Audit  │
   └─────┬─────┘  └─────┬─────┘  └────┬──────┘
         │              │             │
         └──────────────┴─────────────┤
                                      ▼
                              ┌───────────────┐
                              │  AUDIT LOG    │
                              │ (THEMIS engine)│
                              └───────┬───────┘
                                      │
                              ┌───────▼───────┐
                              │  RAG ENGINE   │
                              │ POST /api/query│
                              └───────────────┘
```

### Agent Breakdown

| Agent | Role | Key Capability |
|-------|------|---------------|
| **HERMES** | Autonomous Procurement | Scores vendors across 17 variables, raises POs, routes for human approval |
| **HEPHAESTUS CORE** | Shop Floor Scheduling | Rebalances production schedules, predicts machine failures 72 hours ahead |
| **THEMIS** | Compliance & Audit | 47 regulatory frameworks, natural-language audit trail, full reversibility |
| **RAG Engine** | Intelligence Layer | Intent classification + context retrieval over live agent state |

---

## 🤖 Natural Language Interface (RAG)

HEPHAESTUS exposes a `/api/query` endpoint that answers questions in plain English by retrieving live context from agent state.

**Try it:**

```bash
curl -X POST https://hephaestus-agentic-ai-production.up.railway.app/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Which machine is most likely to fail?"}'
```

**Supported query types:**

| Question | Intent | Retrieved Context |
|----------|--------|-------------------|
| "Which machine is most likely to fail?" | machine_health | Live sensor data + health index |
| "What's our biggest supply chain risk?" | inventory | Stock levels + days-remaining calc |
| "Should we order more Carbon Fibre Panels?" | inventory | Reorder point vs current stock |
| "How many POs are pending approval?" | procurement | Order queue state |
| "Are we compliant with ISO 9001?" | compliance | THEMIS audit results |
| "What's our current OEE trend?" | throughput | 8-cycle throughput history |
| "What jobs are running right now?" | schedule | FORGE production schedule |
| "Give me a status overview" | status | All agents combined |

**Architecture:**

```
User question → Intent classifier (keyword scoring)
              → Context retriever (pulls relevant STATE)
              → Answer generator (rule-based or Claude Haiku)
              → THEMIS audit log entry
              → JSON response with sources
```

The engine works **zero-config** out of the box using rule-based grounded answers. Set the `ANTHROPIC_API_KEY` environment variable to upgrade to Claude Haiku-powered natural language responses.

---

## 🚀 Simulated Performance Metrics

| Metric | HEPHAESTUS | Industry Baseline |
|--------|-----------|-------------------|
| Procurement cycle time | 6.7 hours | 4.2 days |
| Procurement error rate | 0.003% | 2.1% |
| Vendor cost optimization | 12.3% savings | — |
| Schedule adherence | 91.4% | 67% |
| Unplanned downtime reduction | 43% | — |
| Failure prediction lead time | 72 hours | Reactive only |

---

## 📊 Real Data Integration

HEPHAESTUS loads real datasets from Kaggle to power its decision-making:

- **Machine Health Dataset** — sensor readings, vibration, temperature, failure history
- **DataCo Supply Chain Dataset** — vendor performance, lead times, pricing, regional risk

When the `/data` folder is populated, agents operate on real numbers. When it isn't, they fall back to high-fidelity simulation. The same code path runs both.

---

## 📁 Project Structure

```
hephaestus-agentic-ai/
│
├── app.py                  # FastAPI server, all REST endpoints
├── rag_engine.py           # Natural language query engine
├── data_loader.py          # Kaggle dataset loader (machine + supply chain)
├── hephaestus_prototype.py # Original CLI multi-agent system
│
├── static/
│   └── index.html          # Live dashboard frontend
│
├── data/                   # Kaggle datasets (gitignored, download separately)
├── images/                 # Dashboard screenshots
│
├── railway.toml            # Railway deployment config
├── requirements.txt        # Python dependencies
├── .gitignore
└── README.md
```

---

## ⚙️ Run Locally

```bash
# 1. Clone the repo
git clone https://github.com/nagasaitankasala2000-spec/hephaestus-agentic-ai.git
cd hephaestus-agentic-ai

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the API server
python app.py

# 4. Open the dashboard
open http://localhost:8000
```

API docs at `http://localhost:8000/docs`.

---

## 🌐 Deploy Your Own

This repo is ready to deploy on Railway in one click:

1. Fork the repo
2. Sign in at [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
3. Select your fork → Railway auto-detects Python and reads `railway.toml`
4. (Optional) Add `ANTHROPIC_API_KEY` env var to enable LLM-powered RAG
5. Generate domain → live URL in ~3 minutes

---

## 🔑 Key Design Patterns

- **Multi-agent architecture** — each agent owns a distinct domain with no tight coupling
- **Shared audit log** — every agent writes to a single audit infrastructure (THEMIS owns it)
- **Dataclass-driven models** — `ProcurementOrder`, `ProductionJob`, `ComplianceReport` fully typed
- **Composite scoring** — vendor selection uses weighted multi-variable scoring across 5 dimensions
- **Status state machine** — each agent tracks `IDLE → THINKING → EXECUTING → WAITING → COMPLETE`
- **Separation of concerns** — orchestrator coordinates, agents own domain logic
- **Graceful degradation** — falls back to simulation if real data unavailable; falls back to rule-based RAG if no LLM key
- **Grounded answers** — every RAG response cites the specific context blocks it used

---

## 🔭 What This Demonstrates

- Designing and implementing a **multi-agent AI system** from scratch
- Understanding of **industrial enterprise workflows** — procurement, scheduling, compliance
- **Agentic AI patterns** — autonomous decision-making with human-in-the-loop approval gates
- **Audit-first design** — every action logged, explainable, and reversible before execution
- **RAG implementation** — intent classification + context retrieval over structured live data
- **Full-stack deployment** — FastAPI backend, vanilla JS dashboard, public cloud hosting
- Mapping **real-world business processes** to software architecture

---

## 🗺️ Roadmap

- [x] FastAPI backend with all three agents exposed via REST
- [x] Live dashboard with real-time metrics
- [x] Real Kaggle dataset integration (machine health + supply chain)
- [x] RAG natural language query layer
- [x] Public deployment on Railway
- [ ] In-dashboard chat UI for the RAG endpoint
- [ ] Connect HERMES to a real ERP API (SAP, Oracle NetSuite) via REST
- [ ] PostgreSQL backend so state persists across restarts
- [ ] Authentication and role-based access control
- [ ] Inter-agent messaging via async queues
- [ ] Containerize with Docker for portable deployment

---

## 💡 Industry Context

This project was inspired by a gap analysis of the enterprise AI market (2025–2026):

- **Microsoft Copilot** — broad and horizontal, no industrial depth
- **Salesforce Agentforce** — front office only, no manufacturing footprint
- **ServiceNow Now Assist** — IT/HR scope, no shop floor capability
- **The gap** — agentic AI that executes inside manufacturing, supply chain, and procurement workflows with enterprise-grade compliance. Nobody owns this space yet.

HEPHAESTUS is a working prototype of what that should look like.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 · FastAPI · Uvicorn |
| Data | pandas · NumPy · scikit-learn |
| RAG | Custom intent classifier · context retriever · optional Claude Haiku via Anthropic API |
| Frontend | Vanilla HTML/CSS/JS · Chart.js |
| Deployment | Railway · GitHub auto-deploy |
| Datasets | Kaggle (machine health + DataCo supply chain) |

---

## 👤 Author

**Naga Sai Tankasala** — MS IT Project Management (Indiana Wesleyan University) | MS Business Analytics (Sacred Heart University) | B.Tech Mechanical Engineering

Targeting: Process Improvement Analyst | Business Process Architect | Industry 4.0 Transformation roles at Siemens · Accenture · Capgemini · Deloitte · Honeywell · PTC · Pratt & Whitney

📍 Connecticut, USA  
🔗 [LinkedIn](https://www.linkedin.com/) · [GitHub](https://github.com/nagasaitankasala2000-spec)

---

## 📄 License

MIT License — free to use, extend, and build on.
