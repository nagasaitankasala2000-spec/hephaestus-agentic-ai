# HEPHAESTUS

HEPHAESTUS is an event-driven, multi-agent simulation of an EV battery gigafactory.  
It demonstrates how distributed systems, autonomous agents, and machine learning models operate over a shared event-driven architecture.

The system combines a factory simulator, operational agents, predictive ML models, and a real-time dashboard.

---

## Live System
https://hephaestus-agentic-ai-production.up.railway.app

---

## System Design

The system models a manufacturing environment where independent agents react to streaming factory events.

Core principles:
- Event-driven architecture
- Decoupled multi-agent design
- Shared state coordination
- ML integrated into operational workflows
- Real-time observability

---

## Factory Simulation

A 9-stage production pipeline:

Mixing → Coating → Calendering → Slitting → Assembly → Electrolyte Fill → Formation → Aging → Grading

Simulation characteristics:
- Time-compressed execution (1 sec = 1 hour)
- Equipment degradation modeling
- Material consumption and bottlenecks
- Yield variation and scrap generation
- Maintenance cycles

---

## Agents

### FORGE — Quality Risk Model
Predicts failure probability for cells exiting coating.

- XGBoost classifier
- 25,000 synthetic samples
- 14 features
- 95.18% accuracy | 0.921 AUC

---

### HERMES — Supply Chain Agent
Manages procurement and inventory flows.

- 17 suppliers
- 6 materials
- Auto-reorder thresholds
- Purchase order lifecycle tracking

---

### THEMIS — Compliance Engine
Monitors regulatory compliance across the system.

Frameworks:
- UN 38.3
- IATF 16949
- ISO 14001

Automatically opens and resolves findings based on system state.

---

### ORACLE — Query Layer
Lightweight operational query system.

- Structured state queries
- Keyword retrieval
- Context-aware responses

---

## Architecture

Factory Simulator → Event Bus → State Store → FORGE / HERMES / THEMIS → FastAPI → Dashboard

---

## Dashboard

Modules:
- Executive KPIs
- Operations monitoring
- Production flow visualization
- Procurement tracking
- Compliance monitoring
- ML insights (FORGE)

Stack:
- Vanilla HTML/CSS/JS
- Plotly

---

## Key Engineering Concepts

- Event-driven distributed systems
- Pub/Sub messaging model
- Multi-agent coordination
- Shared state management
- ML inference pipelines
- Simulation-based system design
- REST API architecture
- Real-time dashboards

---

## Scope

This is a simulation system, not a production industrial platform.

Limitations:
- Synthetic data only
- No ERP/MES integration
- Simplified physical modeling
- In-memory state store

---

## Tech Stack

Backend:
- Python, FastAPI, Uvicorn

ML / Data:
- Pandas, NumPy
- Scikit-learn, XGBoost

Frontend:
- HTML, CSS, JavaScript
- Plotly

Deployment:
- Railway

---

## Running Locally

git clone https://github.com/nagasaitankasala2000-spec/hephaestus-agentic-ai.git  
cd hephaestus-agentic-ai  
pip install -r requirements.txt  
python app.py  

App:
http://localhost:8000

API Docs:
http://localhost:8000/docs

---

## Engineering Summary

Complex industrial behavior is decomposed into:
- Independent event-driven agents
- Shared operational state
- Predictive ML components
- Observability-first architecture

---

## Author

Naga Sai Tankasala  
MS Information Technology (Project Management) — Indiana Wesleyan University  
MS Business Analytics — Sacred Heart University  
B.Tech Mechanical Engineering  
Connecticut, USA  

---

## License

MIT
