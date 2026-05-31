"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — Synthetic Training Data Generator                       ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Generates realistic cell-level production data for training the yield   ║
║  prediction model. Grounded in published lithium-ion battery research.   ║
║                                                                           ║
║  Why synthetic: real cell-level production data is proprietary to        ║
║  manufacturers. The architecture works identically with real data        ║
║  if available.                                                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import random
import csv
from pathlib import Path
from typing import List, Dict

# All process measurements captured during stages 2-6, BEFORE Formation.
# These are the features the model uses to predict QC failure.
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

TARGET = "failed_qc"  # 1 if cell failed Final Grading, 0 if passed


def generate_one_cell() -> Dict[str, float]:
    """Generate one synthetic cell with realistic process measurements."""
    if random.random() < 0.85:
        base_quality = random.gauss(0.95, 0.04)
    else:
        base_quality = random.gauss(0.78, 0.10)
    base_quality = max(0.40, min(1.0, base_quality))

    nf = 1.0 + (1.0 - base_quality) * 4.0

    cell = {
        "coating_thickness_um":     round(random.gauss(78.0, 1.2 * nf), 2),
        "coating_uniformity_cv":    round(abs(random.gauss(1.0, 0.4 * nf)), 3),
        "coating_areal_mass":       round(random.gauss(22.0, 0.6 * nf), 2),
        "coating_defect_density":   round(random.expovariate(1.0 / (0.4 + (1 - base_quality) * 2.5)), 2),
        "calendering_density":      round(random.gauss(3.5, 0.04 * nf), 3),
        "calendering_porosity":     round(random.gauss(30.0, 1.2 * nf), 2),
        "calendering_force":        round(random.gauss(6000.0, 150.0 * nf), 1),
        "slitting_edge_burr":       round(abs(random.gauss(2.5, 0.8 * nf)), 2),
        "slitting_width_accuracy":  round(abs(random.gauss(0.0, 0.04 * nf)), 4),
        "assembly_winding_tension": round(random.gauss(15.0, 0.4 * nf), 2),
        "assembly_weld_strength":   round(random.gauss(180.0, 7.0 * nf), 1),
        "assembly_initial_resistance": round(random.gauss(12.0, 0.6 * nf), 2),
        "fill_electrolyte_volume":  round(random.gauss(15.0, 0.18 * nf), 3),
        "fill_seal_pressure":       round(random.gauss(120.0, 3.5 * nf), 1),
    }

    failure_probability = _failure_probability(cell, base_quality)
    cell[TARGET] = 1 if random.random() < failure_probability else 0
    return cell


def _failure_probability(cell: dict, base_quality: float) -> float:
    """Map process measurements → failure probability (real physics)."""
    risk = 0.0

    thickness_deviation = abs(cell["coating_thickness_um"] - 78.0)
    risk += min(0.20, thickness_deviation * 0.03)

    if cell["coating_uniformity_cv"] > 2.5:
        risk += 0.15
    elif cell["coating_uniformity_cv"] > 1.8:
        risk += 0.05

    risk += min(0.20, cell["coating_defect_density"] * 0.04)

    density_deviation = abs(cell["calendering_density"] - 3.5)
    risk += min(0.10, density_deviation * 1.5)

    if cell["slitting_edge_burr"] > 5.0:
        risk += 0.25
    elif cell["slitting_edge_burr"] > 3.5:
        risk += 0.08

    if cell["assembly_weld_strength"] < 160.0:
        risk += 0.12
    if cell["assembly_initial_resistance"] > 14.0:
        risk += 0.08

    volume_deviation = abs(cell["fill_electrolyte_volume"] - 15.0)
    risk += min(0.10, volume_deviation * 0.3)

    risk += (1.0 - base_quality) * 0.20

    return max(0.015, min(0.95, risk))


def generate_dataset(n_cells: int = 10000, seed: int = 42) -> List[Dict]:
    """Generate a reproducible dataset of n synthetic cells."""
    random.seed(seed)
    return [generate_one_cell() for _ in range(n_cells)]


def save_dataset(dataset: List[Dict], path: str = "ml/training_data.csv") -> None:
    """Persist the dataset to CSV."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = FEATURES + [TARGET]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset)
    print(f"✅ Wrote {len(dataset)} cells to {path}")


def summarize_dataset(dataset: List[Dict]) -> None:
    """Print quick stats."""
    n = len(dataset)
    failures = sum(1 for c in dataset if c[TARGET] == 1)
    failure_rate = 100.0 * failures / n
    print(f"\n=== DATASET SUMMARY ===")
    print(f"Total cells: {n:,}")
    print(f"Failed QC: {failures:,} ({failure_rate:.2f}%)")
    print(f"Passed QC: {n - failures:,} ({100.0 - failure_rate:.2f}%)")
    print(f"Industry baseline: 6-8% failure rate")
    print()


if __name__ == "__main__":
    dataset = generate_dataset(n_cells=10000)
    summarize_dataset(dataset)
    save_dataset(dataset)
