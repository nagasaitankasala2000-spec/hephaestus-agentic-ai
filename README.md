# HEPHAESTUS

A learning project: a multi-agent simulation of an EV battery gigafactory, built to understand how event-driven systems, autonomous agents, and ML models fit together.

I'm a grad student (MS IT Project Management at Indiana Wesleyan), and I built this over many sessions to teach myself things I couldn't learn from coursework: distributed systems, multi-agent coordination, ML integration into operational systems, and full-stack deployment.

**Live demo:** https://hephaestus-agentic-ai-production.up.railway.app

---

## What it is

A simulated battery factory ("TLYB'S Gigafactory") with four agents observing and acting on a live production line:

- **Simulator** — 9 stages (Mixing → Coating → Calendering → Slitting → Assembly → Electrolyte Fill → Formation → Aging → Grading), time-compressed so 1 real second ≈ 1 sim hour. Equipment degrades, materials get consumed, cells advance through stages, scrap happens.
- **FORGE** — An XGBoost model that scores each cell after Formation and flags ones likely to fail QC. AUC 0.90 on the simulator's own distribution.
- **HERMES** — Procurement agent. Tracks 17 suppliers across 6 materials, auto-reorders when inventory drops below 2 days of coverage, runs a full purchase-order lifecycle.
- **THEMIS** — Compliance agent. Monitors 12 rules across 3 regulatory frameworks (UN 38.3, IATF 16949, ISO 14001) and opens/resolves findings automatically.

Everything communicates through an event bus. Six-tab dashboard shows it all in real time.

---

## Why I built it

To force myself to learn things by doing them:

- How does a pub/sub event bus actually work when you're writing one?
- What does it feel like to integrate an ML model into a system that's already running?
- How do you debug a multi-agent system when something goes wrong silently?
- What's the difference between "demo that works in screenshots" and "system that actually does what it claims"?

The third one turned out to be the most valuable lesson.

---

## Real bugs I found and fixed (the actual learning)

**FORGE was secretly broken for weeks.** Predictor expected feature names like `coating_thickness_um`. Simulator emitted `thickness_um`. Predictor silently filled missing names with nominal defaults, scored every cell as "perfect," flagged nothing. The dashboard happily showed "0 cells flagged" and I assumed FORGE was working. It wasn't.

I found it when I noticed inventory bars looked wrong. Pulled the thread, discovered FORGE had been silently failing the whole time. Fixed it by adding a `SIM_TO_MODEL_KEY` translation map, flattening cell measurements when publishing events, and moving the prediction stage to FORMATION (where all 14 features actually exist).

**Sim-clock vs wall-clock confusion.** HERMES was computing PO lifecycle transitions against `event.timestamp`, which was set when the event was constructed (real-world time). But the factory runs on compressed sim-time. So PO transitions needed 4 *real* hours to fire instead of 4 sim-hours. POs got stuck at PLACED forever. Fixed by adding `sim_now_iso` to every event, populated from the factory's sim clock.

**Random scrap meant the ML model couldn't learn.** Cells were scrapped based on `random.random() < base_failure × (2 − quality_score)` — essentially random with respect to the features the model could see. I trained models multiple times and got AUC stuck around 0.62. Eventually realized the problem wasn't the model — the data had no learnable signal. Rewrote the simulator to make failure deterministic from out-of-spec measurements (defined in a new `simulator/specs.py`). After that, AUC jumped to 0.90.

**HERMES inventory thresholds were wrong.** Original formula: `consumption_per_cell × 500 × 0.30`. The "500" was meaningless. For low-consumption materials like electrolyte, the threshold was tiny — production would stall before HERMES reordered. Rewrote it to industry-standard days-of-coverage: keep at least 2 days of inventory at target throughput (48,000 cells/day).

Most of these were hidden for weeks. Honestly the most useful skill the project taught me was learning to not trust dashboards.

---

## Architecture

```
Simulator (factory.py)
    │ publishes events
    ▼
Event Bus ──► State Store
    │
    ├──► FORGE   (scores cells after FORMATION)
    ├──► HERMES  (reorders materials, runs PO lifecycle)
    └──► THEMIS  (checks 12 compliance rules)
                       │
                       └──► FastAPI ──► Dashboard
```

All four agents are independent processes that don't directly call each other. They communicate by publishing/subscribing to typed events on a shared bus.

---

## Dashboard

Six tabs:

- **Executive** — top-level yield, throughput, savings
- **Operations** — equipment health, throughput chart, cells per stage
- **Production** — animated SCADA-style view of the 9-stage line
- **Procurement** — open POs, spend, inventory bars, supplier scorecards
- **Compliance** — findings, framework deep-dives, rule catalog
- **FORGE** — model performance, flagged cells, scrap saved

Built with vanilla HTML/CSS/JS and Plotly. No frontend framework. Dark "hacker terminal" aesthetic.

---

## What this is not

- Not production software
- Not a real factory connected to a real ERP
- Not a benchmark or industry tool
- Not based on real factory data

It's a learning artifact. The simulator generates its own synthetic measurements based on published battery research (Tesla 4680 specs, typical process windows), and the ML model learns from that synthetic distribution. It's coherent and self-consistent, but it's not real.

---

## Known limitations

- Read-only dashboard (no buttons to trigger maintenance, place manual POs, etc.)
- Inventory can theoretically go below zero (simulator doesn't halt MIXING when materials run out)
- All state is in-memory (lost on restart)
- No authentication
- Synthetic data only

---

## Tech stack

Python 3.10, FastAPI, Uvicorn, pandas, numpy, scikit-learn, XGBoost, Plotly (CDN), vanilla HTML/CSS/JS, Railway for hosting.

---

## Run locally

```bash
git clone https://github.com/nagasaitankasala2000-spec/hephaestus-agentic-ai.git
cd hephaestus-agentic-ai
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000

To retrain the model:

```bash
python ml/generate_realistic_training_data.py
python ml/train_yield_model.py
```

---

## What I learned

- Event-driven architecture clicks once you've actually built one
- Multi-agent systems are easier than they look if you keep state out of the agents
- ML in operational systems is mostly about data plumbing, not models
- Sim-clock and wall-clock are different things and you will confuse them
- "Working in the demo" and "actually working" are different states
- Most of the useful debugging time is spent asking "is this number real?"

---

## Author

Naga Sai Tankasala
MS IT Project Management — Indiana Wesleyan University (in progress)
MS Business Analytics — Sacred Heart University
B.Tech Mechanical Engineering
Connecticut, USA

---

## License

MIT
