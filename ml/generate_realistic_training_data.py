"""
ml/generate_realistic_training_data.py — generates training data that
mirrors the live simulator distribution exactly.

Key design: ALWAYS generate measurements for ALL stages, then determine
scrap based on total out-of-spec count across the whole cell. This gives
the model fully-populated rows for both passing and failing cells, so
it can actually learn what bad measurements look like.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import random
from pathlib import Path

from simulator.cell import STAGE_MEASUREMENT_GENERATORS
from simulator.config import STAGES
from simulator.specs import out_of_spec_count
from ml.synthetic_data import FEATURES, TARGET
from ml.data_collector import SIM_TO_MODEL_KEY, DEFAULTS

N_SAMPLES = 30000
OUTPUT_PATH = Path("ml/training_data.csv")


def simulate_one_cell():
    """
    Generate measurements for ALL stages. Compute total out-of-spec count.
    Scrap probability scales sharply with OOS count.
    Returns (measurements_dict, was_scrapped).
    """
    # Wider quality_score distribution gives more variance in measurements
    quality_score = random.uniform(0.5, 1.0)
    measurements = {}
    total_oos = 0

    # Generate measurements for ALL stages (even for cells that would scrap)
    for stage in STAGES:
        gen = STAGE_MEASUREMENT_GENERATORS.get(stage)
        if gen:
            stage_m = gen(quality_score)
            for k, v in stage_m.items():
                measurements[k] = v
            total_oos += out_of_spec_count(stage, stage_m)

    # Scrap probability based on total OOS across the entire cell
    # 0 OOS: 1% scrap (random failures)
    # 1 OOS: ~5%
    # 2 OOS: ~20%
    # 3 OOS: ~50%
    # 4+ OOS: ~85%
    # Lookup-table scrap: failures are 100% caused by OOS measurements
    # No random baseline. Model has clean signal to learn from.
    scrap_table = {0: 0.00, 1: 0.05, 2: 0.40, 3: 0.85}
    scrap_probability = scrap_table.get(total_oos, 0.95)
    scrapped = random.random() < scrap_probability

    return measurements, scrapped


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pass_count = 0
    fail_count = 0
    skipped = 0

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FEATURES + [TARGET])

        for i in range(N_SAMPLES):
            sim_m, scrapped = simulate_one_cell()
            # Translate simulator keys → model keys
            normalized = {}
            for key, value in sim_m.items():
                mapped = SIM_TO_MODEL_KEY.get(key, key)
                normalized[mapped] = value
            row = [normalized.get(f, DEFAULTS[f]) for f in FEATURES]
            row.append(1 if scrapped else 0)
            # Defensive: validate row before writing
            try:
                row = [float(v) for v in row]
            except (ValueError, TypeError):
                skipped += 1
                continue
            if len(row) != len(FEATURES) + 1:
                skipped += 1
                continue
            writer.writerow(row)
            if scrapped:
                fail_count += 1
            else:
                pass_count += 1

    print(f"OK Generated {pass_count + fail_count} samples → {OUTPUT_PATH}")
    print(f"   PASS (shipped): {pass_count:,}  ({100*pass_count/(pass_count+fail_count):.1f}%)")
    print(f"   FAIL (scrapped): {fail_count:,}  ({100*fail_count/(pass_count+fail_count):.1f}%)")
    if skipped:
        print(f"   SKIPPED malformed: {skipped}")


if __name__ == "__main__":
    main()
