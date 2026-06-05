# Known Bugs in HEPHAESTUS v2

## Open

### Bug: Inventory can go below zero
- **Symptom:** Production continues even when materials are exhausted
- **Effect:** Unrealistic; real factories halt without materials
- **Where to start:** `simulator/production_line.py:_process_stage_exit()` — should check material availability before advancing cell, halt MIXING stage if cathode/anode/electrolyte inventory < required

### Bug #3 (original): No control actions / dashboard is read-only
- See Session 11 plan (deferred)

## Closed

- ✅ Bug #1: Equipment health didn't affect production (Session 9A)
- ✅ Bug #2: RAG chat outdated (Session 9B — Oracle hybrid)
- ✅ Bug #4: Procurement tab missing (Session 10)
- ✅ Bug #5: COMPLIANCE tab missing (Session 11)
- ✅ Bug #6: FORGE tab missing (Session 12)
- ✅ Bug A: HERMES PO lifecycle never advanced (Session 13)
  - **Root cause:** `event.timestamp` is wall-clock time, not sim time. HERMES was computing `elapsed_hours` from wall-clock timestamps, so PO transitions PLACED → IN_TRANSIT (4 sim-hours) required 4 REAL hours of wall-clock time to elapse before triggering. In compressed sim time (1 real sec = 1 sim hour), this was effectively never.
  - **Fix:** Added `sim_now_iso: str = ""` field to `BaseEvent`. Factory now passes `sim_now_iso=self.sim_now.isoformat()` when constructing MaterialQualityEvents. HERMES reads `event.sim_now_iso` instead of `event.timestamp` to get the simulator's compressed clock. PO lifecycle now advances in 4 sim-hours = ~4 real-seconds as designed.
  - **Verified:** Ran 5 hours of wall-clock time → 444 POs cycled successfully, all materials replenished, dynamic equilibrium maintained, ELECTROLYTE correctly identified as bottleneck material.
- ✅ Bug B: PO QTY column displayed 0 (Session 13)
  - **Root cause:** Dashboard JS read `po.quantity` but API field is `po.quantity_units`. Field name mismatch.
  - **Fix:** One-line change in static/index.html — `po.quantity` → `po.quantity_units`.
