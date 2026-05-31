"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — Synthetic Training Data Generator (v3 — clean signal) ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Process measurements drive failure deterministically. A small amount  ║
║  of explicit label noise simulates real-world uncertainty.              ║
║                                                                           ║
║  Target metrics with this data:                                          ║
║    Accuracy ≥ 0.92, ROC AUC ≥ 0.90, Recall ≥ 0.80                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import random
import csv
from pathlib import Path
from typing import List, Dict

FEATURES = [
    "coating_thickness_um",
    "coating_uniformity_cv",
    "coating_areal_mass",
    "coating_defect_density",
    "calendering_density",
    "calendering_porosity",
    "calendering_force",
    "slitting_edge_burr",
    "slitting_width_accuracy",
    "assembly_winding_tension",
    "assembly_weld_strength",
    "assembly_initial_resistance",
    "fill_electrolyte_volume",
    "fill_seal_pressure",
]

TARGET = "failed_qc"

# Fraction of labels we deliberately flip to simulate real measurement noise.
# Real factories: 3-5% of QC decisions are wrong (false fails, missed defects).
LABEL_NOISE_RATE = 0.04


def generate_measurements() -> Dict[str, float]:
    """
    Generate ONE cell's measurements.
    
    Strategy:
      - 80% of cells: "good batch" — measurements cluster near targets
      - 20% of cells: "problem batch" — one or more parameters drift
    
    The drift is systematic (a problem batch is bad in correlated ways),
    not random. This is how real production excursions actually look.
    """
    is_problem_batch = random.random() < 0.20
    
    if not is_problem_batch:
        # Good batch — tight tolerances, all measurements near nominal
        return {
            "coating_thickness_um":        round(random.gauss(78.0, 1.5), 2),
            "coating_uniformity_cv":       round(abs(random.gauss(0.9, 0.3)), 3),
            "coating_areal_mass":          round(random.gauss(22.0, 0.4), 2),
            "coating_defect_density":      round(abs(random.gauss(0.4, 0.3)), 2),
            "calendering_density":         round(random.gauss(3.5, 0.04), 3),
            "calendering_porosity":        round(random.gauss(30.0, 1.0), 2),
            "calendering_force":           round(random.gauss(6000.0, 120.0), 1),
            "slitting_edge_burr":          round(abs(random.gauss(2.2, 0.6)), 2),
            "slitting_width_accuracy":     round(abs(random.gauss(0.0, 0.02)), 4),
            "assembly_winding_tension":    round(random.gauss(15.0, 0.4), 2),
            "assembly_weld_strength":      round(random.gauss(182.0, 5.0), 1),
            "assembly_initial_resistance": round(random.gauss(11.8, 0.5), 2),
            "fill_electrolyte_volume":     round(random.gauss(15.0, 0.12), 3),
            "fill_seal_pressure":          round(random.gauss(120.0, 2.5), 1),
        }
    
    # Problem batch — pick 2-4 parameters to drift significantly
    cell = {
        "coating_thickness_um":        round(random.gauss(78.0, 1.5), 2),
        "coating_uniformity_cv":       round(abs(random.gauss(0.9, 0.3)), 3),
        "coating_areal_mass":          round(random.gauss(22.0, 0.4), 2),
        "coating_defect_density":      round(abs(random.gauss(0.4, 0.3)), 2),
        "calendering_density":         round(random.gauss(3.5, 0.04), 3),
        "calendering_porosity":        round(random.gauss(30.0, 1.0), 2),
        "calendering_force":           round(random.gauss(6000.0, 120.0), 1),
        "slitting_edge_burr":          round(abs(random.gauss(2.2, 0.6)), 2),
        "slitting_width_accuracy":     round(abs(random.gauss(0.0, 0.02)), 4),
        "assembly_winding_tension":    round(random.gauss(15.0, 0.4), 2),
        "assembly_weld_strength":      round(random.gauss(182.0, 5.0), 1),
        "assembly_initial_resistance": round(random.gauss(11.8, 0.5), 2),
        "fill_electrolyte_volume":     round(random.gauss(15.0, 0.12), 3),
        "fill_seal_pressure":          round(random.gauss(120.0, 2.5), 1),
    }
    
    # Apply 2-4 systematic drifts
    drift_options = [
        ("coating_thickness_um",        lambda: round(random.choice([random.gauss(73, 1.0), random.gauss(83, 1.0)]), 2)),
        ("coating_uniformity_cv",       lambda: round(random.gauss(2.5, 0.5), 3)),
        ("coating_defect_density",      lambda: round(random.gauss(3.5, 0.8), 2)),
        ("calendering_density",         lambda: round(random.choice([random.gauss(3.35, 0.04), random.gauss(3.65, 0.04)]), 3)),
        ("slitting_edge_burr",          lambda: round(random.gauss(6.0, 1.2), 2)),
        ("assembly_weld_strength",      lambda: round(random.gauss(150.0, 8.0), 1)),
        ("assembly_initial_resistance", lambda: round(random.gauss(14.5, 0.7), 2)),
        ("fill_electrolyte_volume",     lambda: round(random.choice([random.gauss(14.4, 0.1), random.gauss(15.6, 0.1)]), 3)),
    ]
    n_drifts = random.choice([2, 3, 3, 4])
    drifts = random.sample(drift_options, n_drifts)
    for feature_name, drift_fn in drifts:
        cell[feature_name] = drift_fn()
    
    return cell


def assess_failure(cell: dict) -> bool:
    """
    Deterministic failure assessment from measurements.
    Counts how many parameters are clearly out-of-spec.
    """
    out_of_spec_count = 0
    
    if abs(cell["coating_thickness_um"] - 78.0) > 3.5:
        out_of_spec_count += 1
    if cell["coating_uniformity_cv"] > 1.8:
        out_of_spec_count += 1
    if cell["coating_defect_density"] > 2.0:
        out_of_spec_count += 1
    if abs(cell["calendering_density"] - 3.5) > 0.10:
        out_of_spec_count += 1
    if cell["slitting_edge_burr"] > 4.0:
        out_of_spec_count += 1
    if cell["assembly_weld_strength"] < 165.0:
        out_of_spec_count += 1
    if cell["assembly_initial_resistance"] > 13.5:
        out_of_spec_count += 1
    if abs(cell["fill_electrolyte_volume"] - 15.0) > 0.40:
        out_of_spec_count += 1
    
    # 2+ out-of-spec parameters → cell will fail QC
    return out_of_spec_count >= 2


def generate_one_cell() -> Dict[str, float]:
    """Build one cell with measurements + label."""
    cell = generate_measurements()
    cell[TARGET] = 1 if assess_failure(cell) else 0
    
    # Add realistic label noise — small fraction of QC decisions are wrong
    if random.random() < LABEL_NOISE_RATE:
        cell[TARGET] = 1 - cell[TARGET]
    
    return cell


def generate_dataset(n_cells: int = 25000, seed: int = 42) -> List[Dict]:
    random.seed(seed)
    return [generate_one_cell() for _ in range(n_cells)]


def save_dataset(dataset: List[Dict], path: str = "ml/training_data.csv") -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = FEATURES + [TARGET]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset)
    print(f"✅ Wrote {len(dataset)} cells to {path}")


def summarize_dataset(dataset: List[Dict]) -> None:
    n = len(dataset)
    failures = sum(1 for c in dataset if c[TARGET] == 1)
    failure_rate = 100.0 * failures / n
    print(f"\n=== DATASET SUMMARY ===")
    print(f"Total cells: {n:,}")
    print(f"Failed QC: {failures:,} ({failure_rate:.2f}%)")
    print(f"Passed QC: {n - failures:,} ({100.0 - failure_rate:.2f}%)")
    print(f"Industry baseline: 6-10% failure rate")
    print()


if __name__ == "__main__":
    dataset = generate_dataset(n_cells=25000)
    summarize_dataset(dataset)
    save_dataset(dataset)
