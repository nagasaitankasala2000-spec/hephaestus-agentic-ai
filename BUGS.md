# Known Bugs in HEPHAESTUS v2

## Open

### Bug: HERMES batch events fire inconsistently
- **Symptom:** Material batch events should fire every 100 ticks but appear to fire only once after startup
- **Effect:** POs are placed initially (6 POs at startup) but never replenished; inventory drains to zero; PO lifecycle never advances PLACED → IN_TRANSIT → RECEIVED
- **Where to start:** `simulator/factory.py:_maybe_emit_material_batch()`, ticks vs cells counter naming (variable is `_cells_since_last_batch` but increments per tick)
- **Reproduction:** Run app, watch terminal for 📦 BATCH FIRING messages — should appear every ~100 seconds, currently only appears once
- **Note:** Variable naming is misleading — `_cells_since_last_batch` actually counts TICKS, not cells. Real fix might be to rename and reconsider whether it should count cells_completed instead.

### Bug: Inventory can go below zero
- **Symptom:** Production continues even when materials are exhausted
- **Effect:** Unrealistic; real factories halt without materials
- **Where to start:** `simulator/production_line.py:_process_stage_exit()` — should check material availability before advancing cell, halt MIXING stage if cathode/anode/electrolyte inventory < required

### Bug #3 (original): No control actions / dashboard is read-only
- See Session 11 plan (deferred from tonight)

## Closed

- ✅ Bug #1: Equipment health didn't affect production (Session 9A)
- ✅ Bug #2: RAG chat outdated (Session 9B — Oracle hybrid)
- ✅ Bug #4: Procurement tab missing (Session 10)
