"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS RAG ENGINE — Natural Language Interface                         ║
║  Retrieves live context from agent state and generates grounded answers.    ║
║  Works with zero config (rule-based retrieval) or with ANTHROPIC_API_KEY   ║
║  set as an env var for LLM-powered answers.                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import httpx
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────
# INTENT CLASSIFICATION
# ─────────────────────────────────────────────

INTENT_KEYWORDS = {
    "machine_health": [
        "machine", "health", "fail", "failure", "breakdown", "maintenance",
        "downtime", "critical", "sensor", "vibration", "temperature", "cnc",
        "lathe", "press", "weld", "assembly", "forge", "motor", "bearing"
    ],
    "inventory": [
        "inventory", "stock", "material", "shortage", "depleted", "supply",
        "steel", "aluminium", "copper", "titanium", "carbon", "hydraulic",
        "days remaining", "reorder", "run out"
    ],
    "procurement": [
        "vendor", "purchase", "order", "procurement", "hermes", "price",
        "supplier", "cost", "buy", "source", "po", "approved", "pending"
    ],
    "compliance": [
        "compliance", "regulation", "audit", "violation", "themis", "gdpr",
        "iso", "osha", "reach", "sox", "legal", "risk", "flag", "blocked"
    ],
    "throughput": [
        "throughput", "efficiency", "output", "oee", "performance", "yield",
        "utilization", "production rate", "capacity", "trend"
    ],
    "schedule": [
        "schedule", "job", "forge", "shop floor", "production plan",
        "job queue", "shift", "product", "valve", "actuator", "shaft",
        "manifold", "gear", "running", "next"
    ],
    "status": [
        "status", "summary", "overview", "how is", "what is running",
        "agents", "all", "dashboard", "report"
    ],
}


def classify_intent(question: str) -> str:
    """Keyword-based intent classification — fast, zero-dependency."""
    q = question.lower()
    scores = {
        intent: sum(1 for kw in keywords if kw in q)
        for intent, keywords in INTENT_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "status"


# ─────────────────────────────────────────────
# CONTEXT RETRIEVAL — pulls structured facts from live STATE
# ─────────────────────────────────────────────

def retrieve_context(intent: str, state) -> dict:
    """Retrieve the most relevant context blocks for the given intent."""
    ctx = {}

    if intent in ("machine_health", "schedule", "status"):
        ctx["machines"] = state.machines
        ctx["forge_status"] = state.forge_status
        ctx["throughput"] = state.throughput

    if intent in ("inventory", "procurement", "status"):
        ctx["inventory"] = {
            mat: {
                **inv,
                "days_remaining": round(
                    inv["current_stock"] / max(inv["daily_consumption"], 1), 1
                ),
                "risk": (
                    "CRITICAL"
                    if inv["current_stock"] / max(inv["daily_consumption"], 1) < 5
                    else "HIGH"
                    if inv["current_stock"] / max(inv["daily_consumption"], 1) < 14
                    else "OK"
                ),
            }
            for mat, inv in state.inventory.items()
        }
        ctx["orders"] = [
            {
                "order_id": o.order_id,
                "material": o.material,
                "quantity": o.quantity,
                "vendor_name": o.vendor.get("name", "N/A"),
                "estimated_cost": o.estimated_cost,
                "status": o.status,
                "urgency": o.urgency,
            }
            for o in state.orders
        ]

    if intent in ("compliance", "status"):
        ctx["compliance"] = [
            {"regulation": c.regulation, "status": c.status, "score": c.score}
            for c in state.compliance
        ]
        ctx["themis_status"] = state.themis_status

    if intent == "status":
        ctx["session_id"] = state.session_id
        ctx["started_at"] = state.started_at
        ctx["hermes_status"] = state.hermes_status
        ctx["jobs"] = [
            {"job_id": j.job_id, "product": j.product, "priority": j.priority, "status": j.status}
            for j in state.jobs
        ]
        ctx["audit_count"] = len(state.audit_log)

    return ctx


# ─────────────────────────────────────────────
# RULE-BASED ANSWER GENERATION (no LLM needed)
# ─────────────────────────────────────────────

def rule_based_answer(question: str, intent: str, context: dict) -> tuple[str, list]:
    """Generate a grounded answer from retrieved context — no API key required."""
    q = question.lower()
    sources = []

    # ── MACHINE HEALTH ──────────────────────────────────────────────────────
    if intent == "machine_health":
        machines = context.get("machines", [])
        if not machines:
            return "No machine data available. Run HEPHAESTUS CORE to initialize shop floor state.", []

        worst = min(machines, key=lambda m: m["health"])
        critical = [m for m in machines if m["health"] < 40]
        degraded = [m for m in machines if 40 <= m["health"] < 70]
        healthy = [m for m in machines if m["health"] >= 70]

        sources = [f"{m['name']}: {m['health']}% health" for m in machines]

        if any(kw in q for kw in ["fail", "most likely", "risk", "worst", "danger"]):
            status = (
                "CRITICAL — immediate shutdown recommended"
                if worst["health"] < 40
                else "DEGRADED — preventive maintenance within 48 hours"
                if worst["health"] < 70
                else "NOMINAL"
            )
            return (
                f"⚠️ Highest failure risk: {worst['name']} at {worst['health']}% health. "
                f"Status: {status}. "
                f"Fleet summary: {len(healthy)} healthy, {len(degraded)} degraded, {len(critical)} critical."
            ), sources

        if critical:
            names = ", ".join(m["name"] for m in critical)
            return (
                f"🔴 CRITICAL: {len(critical)} machine(s) require immediate attention — {names}. "
                f"{len(healthy)} machines running normally."
            ), sources

        avg = sum(m["health"] for m in machines) / len(machines)
        return (
            f"Fleet health: {avg:.1f}% average across {len(machines)} machines. "
            f"{len(healthy)} nominal, {len(degraded)} degraded, {len(critical)} critical."
        ), sources

    # ── INVENTORY ───────────────────────────────────────────────────────────
    elif intent == "inventory":
        inventory = context.get("inventory", {})
        if not inventory:
            return "Inventory data not loaded.", []

        critical = [(mat, inv) for mat, inv in inventory.items() if inv["risk"] == "CRITICAL"]
        high = [(mat, inv) for mat, inv in inventory.items() if inv["risk"] == "HIGH"]
        sources = [
            f"{mat}: {inv['current_stock']} {inv['unit']} ({inv['days_remaining']} days) — {inv['risk']}"
            for mat, inv in inventory.items()
        ]

        if any(kw in q for kw in ["shortage", "run out", "critical", "urgent", "lowest"]):
            if critical:
                item, inv = critical[0]
                return (
                    f"🔴 Critical shortage: {item} — only {inv['days_remaining']} days of stock remaining "
                    f"({inv['current_stock']} {inv['unit']}). Trigger HERMES immediately."
                ), sources
            elif high:
                names = ", ".join(m for m, _ in high)
                return f"⚠️ High-risk items: {names}. Reorder within 14 days.", sources
            else:
                return "✅ No critical shortages. All materials above safe thresholds.", sources

        if critical:
            names = ", ".join(m for m, _ in critical)
            return (
                f"🔴 {len(critical)} critical shortage(s): {names}. "
                f"{len(high)} high-risk items. Run HERMES to raise purchase orders."
            ), sources
        elif high:
            names = ", ".join(m for m, _ in high)
            return f"⚠️ {len(high)} item(s) approaching reorder point: {names}.", sources
        else:
            return f"✅ All {len(inventory)} inventory items are within safe thresholds.", sources

    # ── PROCUREMENT ─────────────────────────────────────────────────────────
    elif intent == "procurement":
        orders = context.get("orders", [])
        if not orders:
            return (
                "No purchase orders raised yet. Run HERMES to scan inventory and raise orders automatically."
            ), []

        pending = [o for o in orders if o["status"] == "PENDING_APPROVAL"]
        executed = [o for o in orders if o["status"] == "APPROVED_AND_EXECUTED"]
        total_cost = sum(o["estimated_cost"] for o in executed)

        sources = [
            f"{o['order_id']}: {o['material']} × {o['quantity']} from {o['vendor_name']} — ${o['estimated_cost']:,.2f} [{o['status']}]"
            for o in orders[:5]
        ]

        return (
            f"📦 {len(orders)} purchase orders total. "
            f"{len(pending)} pending approval, {len(executed)} executed. "
            f"Total committed spend: ${total_cost:,.2f}. "
            + (f"Next action: approve {len(pending)} pending order(s)." if pending else "All orders processed.")
        ), sources

    # ── COMPLIANCE ──────────────────────────────────────────────────────────
    elif intent == "compliance":
        checks = context.get("compliance", [])
        if not checks:
            return "No compliance audit run yet. Trigger THEMIS to check all regulatory frameworks.", []

        violations = [c for c in checks if c["status"] == "FAIL"]
        passed = [c for c in checks if c["status"] == "PASS"]
        sources = [f"{c['regulation']}: {c['status']} (score: {c['score']})" for c in checks]

        if violations:
            names = ", ".join(c["regulation"] for c in violations)
            return (
                f"⚠️ {len(violations)} compliance violation(s) detected: {names}. "
                f"{len(passed)} frameworks passing. Immediate remediation recommended."
            ), sources
        else:
            return f"✅ All {len(checks)} regulatory frameworks passing. Last audit confirmed compliance.", sources

    # ── THROUGHPUT ──────────────────────────────────────────────────────────
    elif intent == "throughput":
        tp = context.get("throughput", [])
        if not tp:
            return "No throughput data available yet. Run HEPHAESTUS CORE to collect OEE metrics.", []

        current = tp[-1]
        trend = "↑ improving" if len(tp) > 1 and tp[-1] > tp[-2] else "↓ declining"
        avg = sum(tp) / len(tp)
        vs_baseline = current - 67.0  # industry baseline

        sources = [f"OEE history: {tp}"]
        return (
            f"📊 Current OEE: {current}%. Trend: {trend}. "
            f"Session average: {avg:.1f}%. "
            f"{'+' if vs_baseline >= 0 else ''}{vs_baseline:.1f}% vs industry baseline of 67%."
        ), sources

    # ── SCHEDULE ────────────────────────────────────────────────────────────
    elif intent == "schedule":
        machines = context.get("machines", [])
        jobs = context.get("jobs", []) if "jobs" in context else []

        if not machines:
            return "No shop floor data available.", []

        available = [m for m in machines if m["health"] > 40]
        sources = [f"{m['name']}: {m['health']}% health" for m in machines]

        if not jobs:
            return (
                f"No jobs scheduled yet. {len(available)}/{len(machines)} machines available. "
                f"Run HEPHAESTUS CORE to generate the production schedule."
            ), sources

        critical_jobs = [j for j in jobs if j.get("priority") == "CRITICAL"]
        return (
            f"🏭 {len(jobs)} jobs in schedule. {len(critical_jobs)} critical priority. "
            f"{len(available)} machines available (health > 40%). "
            f"Schedule adherence target: 91.4%."
        ), sources + [f"{j['job_id']}: {j['product']} [{j['priority']}]" for j in jobs[:3]]

    # ── STATUS / DEFAULT ─────────────────────────────────────────────────────
    else:
        machines = context.get("machines", [])
        avg_health = sum(m["health"] for m in machines) / len(machines) if machines else 0
        orders = context.get("orders", [])
        checks = context.get("compliance", [])

        return (
            f"🔥 HEPHAESTUS Session {context.get('session_id', 'N/A')}\n"
            f"Machines: {len(machines)} online | Avg health: {avg_health:.0f}%\n"
            f"Orders: {len(orders)} raised | Audit entries: {context.get('audit_count', 0)}\n"
            f"Compliance: {len([c for c in checks if c['status']=='FAIL'])} violation(s) | "
            f"{len([c for c in checks if c['status']=='PASS'])} passing\n"
            f"Agents — HERMES: {context.get('hermes_status','—')} | "
            f"FORGE: {context.get('forge_status','—')} | "
            f"THEMIS: {context.get('themis_status','—')}"
        ), []


# ─────────────────────────────────────────────
# LLM-POWERED ANSWER (optional — uses Anthropic API if key is set)
# ─────────────────────────────────────────────

async def llm_answer(question: str, intent: str, context: dict, api_key: str) -> Optional[str]:
    """
    Use Claude to generate a rich natural language answer over the retrieved context.
    Only called if ANTHROPIC_API_KEY is set in environment.
    """
    system_prompt = (
        "You are THEMIS, the compliance and intelligence agent of Project HEPHAESTUS — "
        "an industrial AI system for manufacturing operations. "
        "You answer questions about machine health, inventory, procurement, compliance, "
        "and production schedules using ONLY the live context data provided. "
        "Be concise (2-4 sentences), use emoji sparingly for status indicators, "
        "and always ground your answer in the specific numbers from context."
    )

    user_message = (
        f"Question: {question}\n\n"
        f"Live system context (JSON):\n{json.dumps(context, indent=2, default=str)}\n\n"
        f"Detected intent: {intent}\n\n"
        "Answer the question based only on the context above."
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_message}],
                },
            )
            if response.status_code == 200:
                data = response.json()
                return data["content"][0]["text"]
    except Exception as e:
        print(f"[RAG] LLM call failed, falling back to rule-based: {e}")
    return None


# ─────────────────────────────────────────────
# PUBLIC INTERFACE
# ─────────────────────────────────────────────

async def answer(question: str, state) -> dict:
    """
    Main entry point. Returns:
        {
            "answer": str,
            "intent": str,
            "sources": list[str],
            "mode": "llm" | "rule-based"
        }
    """
    intent = classify_intent(question)
    context = retrieve_context(intent, state)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    mode = "rule-based"
    answer_text = None

    if api_key:
        answer_text = await llm_answer(question, intent, context, api_key)
        if answer_text:
            mode = "llm"

    if not answer_text:
        answer_text, sources = rule_based_answer(question, intent, context)
    else:
        _, sources = rule_based_answer(question, intent, context)

    return {
        "answer": answer_text,
        "intent": intent,
        "sources": sources,
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
    }
