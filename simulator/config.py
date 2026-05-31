"""
╔══════════════════════════════════════════════════════════════════════════╗
║  TLYB'S Factory Simulator — Configuration                                ║
║  ────────────────────────────────────────────────────────────────────    ║
║  All tunable parameters of the simulator live here.                      ║
║  Tweak numbers without touching logic anywhere else.                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

# ════════════════════════════════════════════════════════════════════════
# TIME COMPRESSION
# ════════════════════════════════════════════════════════════════════════
# How many simulated minutes pass per real-world second?
# 60 = 1 real second = 1 simulated hour (demo-fast, recommended for live demo)
# 30 = 1 real second = 30 simulated minutes
# 1  = real-time (boring to watch, useful for accuracy testing)
SIM_MINUTES_PER_TICK = 60.0

# How often the simulator's main loop runs, in real seconds.
TICK_INTERVAL_SECONDS = 1.0


# ════════════════════════════════════════════════════════════════════════
# PRODUCTION STAGES
# ════════════════════════════════════════════════════════════════════════
# 9 stages from TLYBS_OPERATIONS.md Section 3.
# Order matters — cells advance in this sequence.
STAGES = [
    "MIXING",
    "COATING",
    "CALENDERING",
    "SLITTING",
    "ASSEMBLY",
    "ELECTROLYTE_FILL",
    "FORMATION",
    "AGING",
    "GRADING",
]

# Average duration each cell spends in each stage (in simulated minutes).
# Real values per TLYBS_OPERATIONS.md — kept honest for interview defense.
STAGE_DURATIONS_MIN = {
    "MIXING":            360,     # 6 hours (batch process, but each cell "inherits" mix time)
    "COATING":           30,      # continuous, fast per cell
    "CALENDERING":       15,
    "SLITTING":          10,
    "ASSEMBLY":          0.25,    # 15 seconds per cell — the line's pacing stage
    "ELECTROLYTE_FILL":  4,       # 4 min per cell
    "FORMATION":         900,     # 15 hours — THE BOTTLENECK
    "AGING":             10080,   # 7 days — but cells age in parallel batches
    "GRADING":           5,       # 5 minutes of automated testing
}

# Probability a cell fails QC at each stage (per published battery research).
# Most failures appear at Formation or Grading; earlier stages produce defects
# that cascade downstream.
STAGE_FAILURE_RATES = {
    "MIXING":            0.001,
    "COATING":           0.005,
    "CALENDERING":       0.003,
    "SLITTING":          0.002,
    "ASSEMBLY":          0.008,
    "ELECTROLYTE_FILL":  0.006,
    "FORMATION":         0.025,   # most failures show up here
    "AGING":             0.012,
    "GRADING":           0.005,
}


# ════════════════════════════════════════════════════════════════════════
# LINE CAPACITY
# ════════════════════════════════════════════════════════════════════════
# Max cells in flight at any moment (across all stages).
# Cap exists to prevent unbounded memory growth during long runs.
MAX_CELLS_IN_FLIGHT = 200

# How many new cells the line starts per simulated hour at full throughput.
# Tesla GF1 hits ~95,000/day at peak = ~3,950/hr. TLYB'S half-scale = ~2,000/hr.
# For demo we want visible activity, so we lower this to keep numbers readable.
NEW_CELLS_PER_SIM_HOUR = 25


# ════════════════════════════════════════════════════════════════════════
# EQUIPMENT
# ════════════════════════════════════════════════════════════════════════
# Each piece of equipment in the line. Health starts at 100, drifts down.
EQUIPMENT = [
    {"id": "MIXER-01",        "type": "MIXER",      "stage": "MIXING"},
    {"id": "COATER-01",       "type": "COATER",     "stage": "COATING"},
    {"id": "CALENDER-01",     "type": "CALENDER",   "stage": "CALENDERING"},
    {"id": "SLITTER-01",      "type": "SLITTER",    "stage": "SLITTING"},
    {"id": "WINDER-01",       "type": "WINDER",     "stage": "ASSEMBLY"},
    {"id": "WINDER-02",       "type": "WINDER",     "stage": "ASSEMBLY"},
    {"id": "FILL-STATION-01", "type": "FILLER",     "stage": "ELECTROLYTE_FILL"},
    {"id": "FORMATION-RACK",  "type": "FORMATION",  "stage": "FORMATION"},
    {"id": "GRADER-01",       "type": "GRADER",     "stage": "GRADING"},
]

# Health degrades by this much (percent) per simulated hour of active use.
EQUIPMENT_HEALTH_DECAY_PCT_PER_HR = 0.05


# ════════════════════════════════════════════════════════════════════════
# MATERIALS & SUPPLIERS
# ════════════════════════════════════════════════════════════════════════
# Materials consumed in cell production. Inventory and supplier metadata.
MATERIALS = {
    "NCM_811_CATHODE":  {"unit": "kg",  "consumption_per_cell": 0.18, "cost_per_unit": 28.0},
    "GRAPHITE_ANODE":   {"unit": "kg",  "consumption_per_cell": 0.11, "cost_per_unit": 12.0},
    "ELECTROLYTE":      {"unit": "L",   "consumption_per_cell": 0.015,"cost_per_unit": 60.0},
    "SEPARATOR_FILM":   {"unit": "m2",  "consumption_per_cell": 0.30, "cost_per_unit": 4.5},
    "COPPER_FOIL":      {"unit": "m2",  "consumption_per_cell": 0.20, "cost_per_unit": 8.0},
    "ALUMINUM_FOIL":    {"unit": "m2",  "consumption_per_cell": 0.20, "cost_per_unit": 5.5},
}

# Supplier list with quality variance — each supplier has a baseline
# quality stat and a stability stat. Higher variance suppliers cause more
# downstream yield problems. HERMES will score suppliers using these.
SUPPLIERS = {
    "NCM_811_CATHODE": [
        {"name": "Yibin Chemical (CN)",        "quality_mean": 99.7, "quality_stddev": 0.08},
        {"name": "Umicore Cathode (BE)",       "quality_mean": 99.8, "quality_stddev": 0.05},
        {"name": "POSCO Future M (KR)",        "quality_mean": 99.6, "quality_stddev": 0.12},
    ],
    "GRAPHITE_ANODE": [
        {"name": "BTR New Energy (CN)",        "quality_mean": 99.5, "quality_stddev": 0.10},
        {"name": "Showa Denko (JP)",           "quality_mean": 99.7, "quality_stddev": 0.06},
    ],
    "ELECTROLYTE": [
        {"name": "Capchem Tech (CN)",          "quality_mean": 99.6, "quality_stddev": 0.07},
        {"name": "Mitsubishi Chemical (JP)",   "quality_mean": 99.8, "quality_stddev": 0.04},
    ],
}


# ════════════════════════════════════════════════════════════════════════
# COST CONSTANTS (for scrap-saved-USD calculation)
# ════════════════════════════════════════════════════════════════════════
COST_PER_SCRAPPED_CELL_USD = 45.0  # materials + labor sunk before scrap detected
