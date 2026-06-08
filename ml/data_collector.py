"""
ml/data_collector.py — collects (measurements, was_scrapped) pairs from the
live simulator and writes them to a CSV ready for retraining the yield model.

Called from simulator/factory.py when a cell reaches SHIPPED or SCRAPPED.
"""

import csv
import threading
from pathlib import Path
from typing import Dict

from ml.synthetic_data import FEATURES, TARGET

# Same mapping as ml/yield_predictor.py — keeps the two in sync
SIM_TO_MODEL_KEY = {
    "thickness_um":           "coating_thickness_um",
    "uniformity_cv":          "coating_uniformity_cv",
    "areal_mass_mg_cm2":      "coating_areal_mass",
    "defect_density_per_m2":  "coating_defect_density",
    "density_g_cm3":          "calendering_density",
    "porosity_pct":           "calendering_porosity",
    "calender_force_n_cm":    "calendering_force",
    "edge_burr_um":           "slitting_edge_burr",
    "width_accuracy_mm":      "slitting_width_accuracy",
    "winding_tension_n":      "assembly_winding_tension",
    "weld_strength_n":        "assembly_weld_strength",
    "initial_resistance_mohm":"assembly_initial_resistance",
    "electrolyte_volume_ml":  "fill_electrolyte_volume",
    "seal_pressure_psi":      "fill_seal_pressure",
}

DEFAULTS = {
    "coating_thickness_um":        78.0,
    "coating_uniformity_cv":       1.0,
    "coating_areal_mass":          22.0,
    "coating_defect_density":      0.4,
    "calendering_density":         3.5,
    "calendering_porosity":        30.0,
    "calendering_force":           6000.0,
    "slitting_edge_burr":          2.2,
    "slitting_width_accuracy":     0.02,
    "assembly_winding_tension":    15.0,
    "assembly_weld_strength":      182.0,
    "assembly_initial_resistance": 11.8,
    "fill_electrolyte_volume":     15.0,
    "fill_seal_pressure":          120.0,
}

OUTPUT_PATH = Path("ml/collected_data.csv")
_lock = threading.Lock()
_initialized = False
_rows_written = 0


def _init_csv():
    """Write CSV header on first call."""
    global _initialized
    if _initialized:
        return
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FEATURES + [TARGET])
    _initialized = True


def record_cell(measurements: Dict[str, float], was_scrapped: bool) -> None:
    """
    Record one labeled training sample.
    measurements: flat dict from cell.measurements (simulator-side keys)
    was_scrapped: True if cell was scrapped before SHIPPED
    """
    global _rows_written
    with _lock:
        _init_csv()
        # Translate simulator keys → model keys, fill missing with defaults
        normalized = {}
        for key, value in measurements.items():
            mapped = SIM_TO_MODEL_KEY.get(key, key)
            normalized[mapped] = value
        row = [normalized.get(f, DEFAULTS[f]) for f in FEATURES]
        row.append(1 if was_scrapped else 0)
        with open(OUTPUT_PATH, "a", newline="") as f:
            csv.writer(f).writerow(row)
        _rows_written += 1


def rows_written() -> int:
    return _rows_written
