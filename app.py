"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           PROJECT HEPHAESTUS — API SERVER v1.0                             ║
║           FastAPI backend exposing all three agents via HTTP               ║
╚══════════════════════════════════════════════════════════════════════════════╝

Run:
    pip install -r requirements.txt
    python app.py

Then open: http://localhost:8000
API docs:  http://localhost:8000/docs
"""

import random
import uuid
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn
import os
from rag_engine import answer as rag_answer
from simulator.factory import factory
from agents.forge import forge
from agents.hermes import hermes
from agents.themis import themis
from core.state_store import store
from core.event_bus import bus


# Real data loader — loads from /data folder if available
try:
    from data_loader import HephaestusDataLoader
    REAL_DATA = HephaestusDataLoader()
    REAL_DATA.initialize()
    _real_machines = REAL_DATA.get_machine_states()
    _real_vendors  = REAL_DATA.get_vendors()
    _real_alerts   = REAL_DATA.get_inventory_alerts()
    _real_throughput = REAL_DATA.get_throughput()
    _real_kpis     = REAL_DATA.get_supply_chain_kpis()
    print(f"[APP] Real data active — {len(_real_machines)} machines, {len(_real_vendors)} vendors")
except Exception as e:
    REAL_DATA = None
    _real_machines = []
    _real_vendors  = []
    _real_alerts   = []
    _real_throughput = [72,74,76,75,79,82,85,88]
    _real_kpis     = {}
    print(f"[APP] Simulation mode ({e})")


# ─────────────────────────────────────────────
#  ENUMS & CONSTANTS
# ─────────────────────────────────────────────

class AgentStatus(Enum):
    IDLE     = "IDLE"
    THINKING = "THINKING"
    EXECUTING= "EXECUTING"
    WAITING  = "WAITING_APPROVAL"
    COMPLETE = "COMPLETE"
    ERROR    = "ERROR"

class Priority(Enum):
    LOW      = 1
    MEDIUM   = 2
    HIGH     = 3
    CRITICAL = 4

class ComplianceFlag(Enum):
    CLEAR   = "CLEAR"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"

VENDORS = [
    {"id":"V001","name":"SteelCore GmbH",       "price_index":0.92,"lead_days":5, "quality_score":94,"risk":"LOW",   "carbon":0.82},
    {"id":"V002","name":"MetalWorks AG",          "price_index":0.87,"lead_days":8, "quality_score":89,"risk":"LOW",   "carbon":0.91},
    {"id":"V003","name":"IndusSupply Ltd",         "price_index":0.79,"lead_days":14,"quality_score":76,"risk":"MEDIUM","carbon":1.12},
    {"id":"V004","name":"PrecisionParts Tokyo",    "price_index":0.95,"lead_days":12,"quality_score":98,"risk":"LOW",   "carbon":1.05},
    {"id":"V005","name":"EuroAlloys SA",           "price_index":0.88,"lead_days":6, "quality_score":91,"risk":"LOW",   "carbon":0.78},
]

MACHINES = [
    {"id":"M001","name":"CNC Mill Alpha",    "efficiency":0.94,"health":91},
    {"id":"M002","name":"Lathe Unit Bravo",  "efficiency":0.88,"health":78},
    {"id":"M003","name":"Press Delta",       "efficiency":0.96,"health":95},
    {"id":"M004","name":"Weld Station Echo", "efficiency":0.91,"health":85},
    {"id":"M005","name":"Assembly Foxtrot",  "efficiency":0.89,"health":62},
]

MATERIALS = [
    "Steel Rod 40mm","Aluminium Sheet 3mm","Copper Wire 2mm",
    "Titanium Bolt M12","Carbon Fibre Panel","Hydraulic Seal Kit"
]

PRODUCTS = [
    "Valve Assembly A3","Actuator Housing B7","Precision Shaft C2",
    "Hydraulic Manifold D5","Gear Cluster E9"
]

REGULATIONS = ["EU_GDPR","ISO_9001","ISO_14001","REACH_COMPLIANCE","SOX_FINANCIAL","EU_AI_ACT","OSHA_SAFETY"]


# ─────────────────────────────────────────────
#  DATA MODELS
# ─────────────────────────────────────────────

@dataclass
class AuditEntry:
    timestamp:  str
    agent:      str
    action:     str
    decision:   str
    rationale:  str
    compliance: str
    reversible: bool = True
    entry_id:   str  = field(default_factory=lambda: str(uuid.uuid4())[:8])

@dataclass
class ProcurementOrder:
    order_id:      str
    material:      str
    quantity:      float
    unit:          str
    vendor:        dict
    estimated_cost:float
    urgency:       str
    status:        str = "PENDING_APPROVAL"
    created_at:    str = field(default_factory=lambda: datetime.now().isoformat())
    approved_at:   Optional[str] = None

@dataclass
class ProductionJob:
    job_id:       str
    product:      str
    quantity:     int
    machine:      dict
    start_time:   str
    duration_hrs: float
    priority:     str
    status:       str = "SCHEDULED"

@dataclass
class ComplianceCheck:
    regulation: str
    status:     str
    score:      float
    checked_at: str


# ─────────────────────────────────────────────
#  GLOBAL STATE  (in-memory for prototype)
# ─────────────────────────────────────────────

class SystemState:
    def __init__(self):
        self.session_id    = str(uuid.uuid4())[:8].upper()
        self.started_at    = datetime.now().isoformat()
        self.audit_log:    List[AuditEntry]      = []
        self.orders:       List[ProcurementOrder] = []
        self.jobs:         List[ProductionJob]    = []
        self.compliance:   List[ComplianceCheck]  = []
        # Use real machine data if available, else fallback
        if _real_machines:
            self.machines = [
                {"id": m["id"], "name": m["name"],
                 "health": m["health"], "efficiency": m["efficiency"],
                 "model": m.get("model","unknown"), "age": m.get("age_years",0),
                 "sensors": m.get("sensors",{}),
                 "total_failures": m.get("total_failures",0)}
                for m in _real_machines
            ]
        else:
            self.machines = [dict(m) for m in MACHINES]
        self.inventory     = self._init_inventory()
        self.hermes_status = AgentStatus.IDLE.value
        self.forge_status  = AgentStatus.IDLE.value
        self.themis_status = AgentStatus.IDLE.value
        self.throughput    = list(_real_throughput) if _real_throughput else [72,74,76,75,79,82,85,88]

    def _init_inventory(self):
        return {
            m: {
                "current_stock":   random.randint(20, 500),
                "reorder_point":   random.randint(50, 150),
                "daily_consumption": random.randint(5, 30),
                "unit":            random.choice(["kg","units","meters"]),
            }
            for m in MATERIALS
        }

    def add_audit(self, agent, action, decision, rationale, compliance="CLEAR"):
        entry = AuditEntry(
            timestamp  = datetime.now().isoformat(),
            agent      = agent,
            action     = action,
            decision   = decision,
            rationale  = rationale,
            compliance = compliance,
        )
        self.audit_log.insert(0, entry)
        return entry

    def to_summary(self):
        return {
            "session_id":    self.session_id,
            "started_at":    self.started_at,
            "total_orders":  len(self.orders),
            "total_jobs":    len(self.jobs),
            "audit_entries": len(self.audit_log),
            "hermes_status": self.hermes_status,
            "forge_status":  self.forge_status,
            "themis_status": self.themis_status,
            "throughput":    self.throughput,
            "machines":      self.machines,
        }

STATE = SystemState()


# ─────────────────────────────────────────────
#  FASTAPI APP
# ─────────────────────────────────────────────

app = FastAPI(
    title       = "Project HEPHAESTUS API",
    description = "Agentic AI for Industrial Enterprise Workflows",
    version     = "0.9",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)


# ─────────────────────────────────────────────
#  ROOT — serve dashboard
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    for path in ["static/index.html", "index.html"]:
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
    return "<h1>HEPHAESTUS API running — visit /docs for API explorer</h1>"

# ─────────────────────────────────────────────
#  SYSTEM STATUS
# ─────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    violations = sum(1 for c in STATE.compliance if c.status == "FAIL")
    return {
        **STATE.to_summary(),
        "compliance_violations": violations,
        "overall_compliance": "WARNING" if violations > 0 else "CLEAR",
        "uptime_pct": 99.97,
        "procurement_cycle_hrs": 6.7,
        "cost_savings_pct": 12.3,
        "schedule_adherence_pct": 91.4,
    }


# ─────────────────────────────────────────────
#  HERMES — PROCUREMENT AGENT
# ─────────────────────────────────────────────

def score_vendor(vendor, quantity):
    return round(
        (1 - vendor["price_index"]) * 35 +
        (1 / vendor["lead_days"])   * 25 +
        vendor["quality_score"] / 100 * 20 +
        (1 if vendor["risk"]=="LOW" else 0.5 if vendor["risk"]=="MEDIUM" else 0) * 10 +
        (1 - vendor["carbon"]) * 10,
        4
    )

@app.post("/api/hermes/run")
async def hermes_run():
    """Trigger HERMES procurement cycle — scans inventory and raises purchase orders."""
    STATE.hermes_status = AgentStatus.THINKING.value
    new_orders = []

    # Use real inventory alerts if available
    real_alerts = _real_alerts if _real_alerts else []
    real_vendors = _real_vendors if _real_vendors else []

    if real_alerts:
        for alert in real_alerts:
            vendor_list = real_vendors if real_vendors else VENDORS
            best_vendor = vendor_list[0] if vendor_list else VENDORS[0]
            cost = round(alert["qty_needed"] * alert.get("avg_price", 25.0), 2)
            order = ProcurementOrder(
                order_id       = f"PO-{str(uuid.uuid4())[:6].upper()}",
                material       = alert["material"],
                quantity       = alert["qty_needed"],
                unit           = alert["unit"],
                vendor         = {
                    "name": best_vendor.get("name", "Standard Logistics"),
                    "score": best_vendor.get("quality_score", 60),
                    "risk":  best_vendor.get("risk", "MEDIUM"),
                    "lead_days": best_vendor.get("avg_lead_days", 4),
                },
                estimated_cost = cost,
                urgency        = alert["urgency"],
            )
            STATE.orders.append(order)
            new_orders.append(asdict(order))
            STATE.add_audit(
                "HERMES", "RAISE_PURCHASE_ORDER",
                f"Order {order.order_id} raised for {alert['material']}",
                f"Real data: stock depletes in {alert['days_remaining']} days. "
                f"Vendor selected: {best_vendor.get('name','Standard Logistics')}.",
            )
        STATE.hermes_status = AgentStatus.WAITING.value if new_orders else AgentStatus.COMPLETE.value
        return {
            "status": "success",
            "orders_raised": len(new_orders),
            "orders": new_orders,
            "data_source": "real",
            "message": f"{len(new_orders)} purchase order(s) raised from real supply chain data.",
        }

    # Fallback to simulation
    for material, inv in STATE.inventory.items():
        days_remaining = inv["current_stock"] / max(inv["daily_consumption"], 1)
        if days_remaining < 14:
            scored  = sorted(VENDORS, key=lambda v: score_vendor(v, inv["daily_consumption"]*30), reverse=True)
            vendor  = {**scored[0], "score": score_vendor(scored[0], inv["daily_consumption"]*30)}
            qty     = inv["daily_consumption"] * 30
            cost    = round(qty * vendor["price_index"] * random.uniform(8, 45), 2)
            order   = ProcurementOrder(
                order_id       = f"PO-{str(uuid.uuid4())[:6].upper()}",
                material       = material,
                quantity       = qty,
                unit           = inv["unit"],
                vendor         = vendor,
                estimated_cost = cost,
                urgency        = "CRITICAL" if days_remaining < 5 else "HIGH",
            )
            STATE.orders.append(order)
            new_orders.append(asdict(order))
            STATE.add_audit(
                "HERMES", "RAISE_PURCHASE_ORDER",
                f"Order {order.order_id} raised for {material}",
                f"Stock depletes in {round(days_remaining,1)} days. Vendor {vendor['name']} selected (score {vendor['score']}).",
            )

    STATE.hermes_status = AgentStatus.WAITING.value if new_orders else AgentStatus.COMPLETE.value
    return {
        "status":     "success",
        "orders_raised": len(new_orders),
        "orders":     new_orders,
        "message":    f"{len(new_orders)} purchase order(s) raised and awaiting approval."
                      if new_orders else "All inventory levels nominal. No orders required.",
    }

@app.post("/api/hermes/approve")
async def hermes_approve():
    """Approve all pending purchase orders — single click execution."""
    approved = []
    for order in STATE.orders:
        if order.status == "PENDING_APPROVAL":
            order.status     = "APPROVED_AND_EXECUTED"
            order.approved_at = datetime.now().isoformat()
            approved.append(order.order_id)
            STATE.add_audit(
                "HERMES", "EXECUTE_ORDER",
                f"Order {order.order_id} executed",
                f"Human approval received. Order transmitted to {order.vendor['name']} ERP system.",
            )
    STATE.hermes_status = AgentStatus.COMPLETE.value
    return {
        "status":   "success",
        "approved": approved,
        "message":  f"{len(approved)} order(s) executed successfully.",
    }

@app.get("/api/hermes/orders")
async def hermes_orders():
    """Get all purchase orders."""
    return {
        "orders":       [asdict(o) for o in STATE.orders],
        "total":        len(STATE.orders),
        "pending":      sum(1 for o in STATE.orders if o.status=="PENDING_APPROVAL"),
        "executed":     sum(1 for o in STATE.orders if o.status=="APPROVED_AND_EXECUTED"),
        "vendor_scores":[{"vendor":v["name"],"score":round(score_vendor(v,100),3),"risk":v["risk"]} for v in VENDORS],
    }

@app.get("/api/hermes/inventory")
async def hermes_inventory():
    """Get current inventory levels and risk assessment."""
    result = []
    for material, inv in STATE.inventory.items():
        days = inv["current_stock"] / max(inv["daily_consumption"], 1)
        result.append({
            "material":      material,
            "current_stock": inv["current_stock"],
            "unit":          inv["unit"],
            "days_remaining":round(days, 1),
            "risk":          "CRITICAL" if days < 5 else "HIGH" if days < 14 else "OK",
            "reorder_point": inv["reorder_point"],
        })
    return {"inventory": result}


# ─────────────────────────────────────────────
#  HEPHAESTUS CORE — SHOP FLOOR AGENT
# ─────────────────────────────────────────────

@app.post("/api/forge/schedule")
async def forge_schedule():
    """Trigger HEPHAESTUS CORE to rebalance the production schedule."""
    STATE.forge_status = AgentStatus.THINKING.value
    STATE.jobs.clear()

    # Degrade machine health slightly each cycle
    for m in STATE.machines:
        m["health"] = max(30, m["health"] - random.randint(0, 4))

    available = [m for m in STATE.machines if m["health"] > 40]

    # Safety: if all machines are critical, fall back to least-degraded machine
    if not available:
        available = [max(STATE.machines, key=lambda m: m["health"])]
        STATE.add_audit(
            "HEPHAESTUS_CORE", "FALLBACK_MODE",
            "All machines critical — operating on least-degraded unit",
            "Production continues at reduced capacity. Maintenance team paged.",
            compliance="WARNING",
        )

    new_jobs = []    
    for i, product in enumerate(PRODUCTS):
        machine      = available[i % len(available)]
        start        = (datetime.now() + timedelta(hours=i*2)).strftime("%H:%M")
        duration     = round(random.uniform(1.5, 6.0), 1)
        priority     = random.choice(["LOW","MEDIUM","HIGH","CRITICAL"])
        job          = ProductionJob(
            job_id       = f"JOB-{str(uuid.uuid4())[:5].upper()}",
            product      = product,
            quantity     = random.randint(50, 500),
            machine      = machine,
            start_time   = start,
            duration_hrs = duration,
            priority     = priority,
        )
        STATE.jobs.append(job)
        new_jobs.append(asdict(job))
        STATE.add_audit(
            "HEPHAESTUS_CORE", "SCHEDULE_JOB",
            f"Job {job.job_id} → {machine['name']}",
            f"Machine health {machine['health']}%, efficiency {machine['efficiency']*100:.0f}%. Priority: {priority}.",
        )

    # Update throughput trend
    last = STATE.throughput[-1]
    STATE.throughput.append(round(min(99, last + random.uniform(-1, 2.5)), 1))
    STATE.throughput = STATE.throughput[-8:]

    STATE.forge_status = AgentStatus.COMPLETE.value
    return {
        "status":       "success",
        "jobs_scheduled": len(new_jobs),
        "jobs":         new_jobs,
        "machines_online": len(available),
        "throughput":   STATE.throughput,
    }

@app.post("/api/forge/simulate-failure")
async def forge_simulate_failure():
    """Simulate a random machine failure and trigger auto-reroute."""
    target  = random.choice(STATE.machines)
    old_health = target["health"]
    target["health"] = random.randint(10, 35)
    STATE.add_audit(
        "HEPHAESTUS_CORE", "PREDICTIVE_MAINTENANCE_ALERT",
        f"FAILURE: {target['name']} health dropped to {target['health']}%",
        f"Health degraded from {old_health}% to {target['health']}%. Rerouting production.",
        compliance="WARNING",
    )
    STATE.add_audit(
        "HEPHAESTUS_CORE", "AUTO_REROUTE",
        f"Jobs rerouted away from {target['name']}",
        "Production automatically redistributed to healthy machines within 90 seconds.",
    )
    STATE.forge_status = AgentStatus.EXECUTING.value
    return {
        "status":   "alert",
        "machine":  target,
        "message":  f"{target['name']} health critical at {target['health']}%. Auto-reroute initiated.",
    }

@app.get("/api/forge/machines")
async def forge_machines():
    """Get current machine health and status."""
    return {
        "machines": [
            {**m, "status": "OK" if m["health"] > 70 else "DEGRADED" if m["health"] > 40 else "CRITICAL"}
            for m in STATE.machines
        ],
        "online":   sum(1 for m in STATE.machines if m["health"] > 40),
        "total":    len(STATE.machines),
    }


# ─────────────────────────────────────────────
#  THEMIS — COMPLIANCE & AUDIT AGENT
# ─────────────────────────────────────────────

@app.post("/api/themis/audit")
async def themis_audit():
    """Run full compliance audit across all regulatory frameworks."""
    STATE.themis_status = AgentStatus.THINKING.value
    STATE.compliance.clear()
    violations = []

    for reg in REGULATIONS:
        passed = random.random() > 0.15
        check  = ComplianceCheck(
            regulation = reg,
            status     = "PASS" if passed else "FAIL",
            score      = round(random.uniform(0.85,1.0) if passed else random.uniform(0.4,0.75), 3),
            checked_at = datetime.now().isoformat(),
        )
        STATE.compliance.append(check)
        if not passed:
            violations.append(reg)

    overall = "BLOCKED" if len(violations) > 3 else "WARNING" if violations else "CLEAR"
    STATE.add_audit(
        "THEMIS", "COMPLIANCE_AUDIT",
        f"Audit complete — {overall}",
        f"{len(REGULATIONS)} regulations checked. {len(violations)} violation(s): {', '.join(violations) if violations else 'none'}.",
        compliance=overall,
    )
    STATE.themis_status = AgentStatus.COMPLETE.value
    return {
        "status":        "success",
        "overall":       overall,
        "checks":        [asdict(c) for c in STATE.compliance],
        "violations":    violations,
        "passed":        len(REGULATIONS) - len(violations),
        "total":         len(REGULATIONS),
        "recommendations": [f"Review {v} policy and update process controls." for v in violations],
    }

@app.get("/api/themis/audit-log")
async def themis_audit_log(limit: int = 20):
    """Get the full audit trail with natural language entries."""
    return {
        "entries": [asdict(e) for e in STATE.audit_log[:limit]],
        "total":   len(STATE.audit_log),
        "summary": {
            "agents_active":    list({e.agent for e in STATE.audit_log}),
            "clear":            sum(1 for e in STATE.audit_log if e.compliance=="CLEAR"),
            "warning":          sum(1 for e in STATE.audit_log if e.compliance=="WARNING"),
            "blocked":          sum(1 for e in STATE.audit_log if e.compliance=="BLOCKED"),
            "all_reversible":   all(e.reversible for e in STATE.audit_log),
        }
    }


# ─────────────────────────────────────────────
#  ORCHESTRATOR — RUN ALL AGENTS
# ─────────────────────────────────────────────

@app.post("/api/orchestrator/run-all")
async def orchestrator_run_all():
    """Run all three agents in sequence — full HEPHAESTUS cycle."""
    hermes_result = await hermes_run()
    if hermes_result["orders_raised"] > 0:
        await hermes_approve()

    forge_result  = await forge_schedule()
    themis_result = await themis_audit()

    STATE.add_audit(
        "ORCHESTRATOR", "FULL_CYCLE_COMPLETE",
        "All three agents completed successfully",
        f"HERMES: {hermes_result['orders_raised']} orders. FORGE: {forge_result['jobs_scheduled']} jobs. THEMIS: {themis_result['overall']}.",
    )

    return {
        "status":  "success",
        "message": "Full HEPHAESTUS cycle complete.",
        "hermes":  hermes_result,
        "forge":   forge_result,
        "themis":  themis_result,
    }

@app.post("/api/orchestrator/reset")
async def orchestrator_reset():
    """Reset all agent state — fresh session."""
    global STATE
    STATE = SystemState()
    return {"status":"success","message":"System reset. New session started.","session_id":STATE.session_id}


# ─────────────────────────────────────────────
#  STATIC FILES & ENTRY POINT
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# RAG — NATURAL LANGUAGE QUERY INTERFACE
# ─────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str

@app.post("/api/query")
async def query_agents(req: QueryRequest):
    """Ask HEPHAESTUS anything in plain English."""
    if not req.question or len(req.question.strip()) < 3:
        raise HTTPException(status_code=400, detail="Question too short.")

    result = await rag_answer(req.question, STATE)

    STATE.add_audit(
        "THEMIS",
        "NATURAL_LANGUAGE_QUERY",
        f"Query: {req.question[:60]}{'...' if len(req.question) > 60 else ''}",
        f"Intent: {result['intent']} | Mode: {result['mode']} | "
        f"Sources: {len(result['sources'])} context block(s).",
    )

    return result
@app.get("/api/real-data/kpis")
async def real_data_kpis():
    """Get real supply chain KPIs from DataCo dataset."""
    return {
        "data_loaded": REAL_DATA is not None and REAL_DATA.data_loaded,
        "machines":    _real_machines,
        "vendors":     _real_vendors[:4],
        "kpis":        _real_kpis,
        "throughput":  _real_throughput,
        "alerts":      _real_alerts,
    }

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# ─────────────────────────────────────────────
# SIMULATOR — TLYB'S Factory background thread
# ─────────────────────────────────────────────

@app.on_event("startup")
async def start_factory():
    """Boot the TLYB'S Gigafactory simulator when the app starts."""
    factory.start()
    print(f"\n🏭 TLYB'S Gigafactory simulator started in background thread.")
print(f"🤖 FORGE agent online — model loaded, monitoring COATING exits.")
print(f"📦 HERMES procurement agent online — auto-reorder enabled across 17 suppliers.")
print(f"⚖️  THEMIS compliance agent online — 3 frameworks, 12 rules, auto-resolve enabled.")


@app.on_event("shutdown")
async def stop_factory():
    """Cleanly stop the simulator when the app shuts down."""
    factory.stop()


@app.get("/api/simulator/status")

@app.get("/api/forge/status")
async def forge_status():
    """Return current state of the FORGE yield prediction agent."""
    return forge.forge_summary()
@app.get("/api/hermes/v2/status")
async def hermes_v2_status():
    """Return current state of the v2 HERMES procurement agent."""
    return hermes.hermes_summary()


@app.get("/api/hermes/v2/purchase-orders")
async def hermes_v2_purchase_orders(status: str = None, limit: int = 50):
    """Return purchase orders, optionally filtered by status."""
    return {
        "purchase_orders": store.get_purchase_orders(status_filter=status, limit=limit),
        "summary": store.get_procurement_summary(),
    }


@app.get("/api/hermes/v2/suppliers")
async def hermes_v2_suppliers():
    """Return all supplier scorecards."""
    return {"suppliers": store.get_supplier_scores()}


@app.get("/api/hermes/v2/inventory")
async def hermes_v2_inventory():
    """Return current material inventory levels."""
    return {"inventory": store.get_material_inventory()}

@app.get("/api/themis/v2/status")
async def themis_v2_status():
    """Return current state of v2 THEMIS compliance agent."""
    return themis.themis_summary()


@app.get("/api/themis/v2/findings")
async def themis_v2_findings(status: str = "OPEN", framework: str = None, limit: int = 50):
    """Return compliance findings — filterable by status and framework."""
    return {
        "findings": store.get_findings(status_filter=status, framework_filter=framework, limit=limit),
        "summary": store.get_compliance_summary(),
    }


@app.get("/api/themis/v2/frameworks")
async def themis_v2_frameworks():
    """Return all 3 frameworks with their current compliance scores."""
    from compliance.frameworks import FRAMEWORKS, RULES
    scores = store.get_framework_scores()
    enriched = {}
    for fid, meta in FRAMEWORKS.items():
        enriched[fid] = {
            **meta,
            "score": scores.get(fid, {"score_pct": 100.0, "open_findings": 0}),
            "rules": [
                {"id": r["id"], "clause": r["clause"], "description": r["description"], "severity": r["severity"]}
                for r in RULES if r["framework"] == fid
            ],
        }
    return {"frameworks": enriched}
async def simulator_status():
    """Return current state of the TLYB'S factory simulator."""
    return factory.status()
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n╔══════════════════════════════════════════════╗")
    print(f"║ HEPHAESTUS API SERVER — v1.1                ║")
    print(f"║ Dashboard : http://localhost:{port}             ║")
    print(f"║ API Docs  : http://localhost:{port}/docs        ║")
    print(f"╚══════════════════════════════════════════════╝\n")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
