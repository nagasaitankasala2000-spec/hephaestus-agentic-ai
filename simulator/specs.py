"""
simulator/specs.py — acceptable measurement ranges per stage.

Cells with measurements outside these ranges are more likely to be scrapped.
This is what makes the production data MEASUREMENT-DRIVEN, so that the FORGE
ML model has a real predictive signal to learn.

Ranges chosen to match the generators in cell.py with ~5-10% out-of-spec rate.
"""

# {stage: {measurement_key: (lo, hi)}}
STAGE_SPECS = {
    "COATING": {
        "thickness_um":           (70.0, 86.0),    # nominal 78 +/- 8
        "uniformity_cv":          (0.0,  3.5),     # lower is better
        "areal_mass_mg_cm2":      (20.0, 24.0),    # nominal 22 +/- 2
        "defect_density_per_m2":  (0.0,  3.0),     # lower is better
    },
    "CALENDERING": {
        "density_g_cm3":          (3.35, 3.65),    # nominal 3.5
        "porosity_pct":           (26.0, 34.0),    # nominal 30 +/- 4
        "calender_force_n_cm":    (5400, 6600),    # nominal 6000 +/- 600
    },
    "SLITTING": {
        "edge_burr_um":           (0.0,  6.0),     # lower is better
        "width_accuracy_mm":      (0.0,  0.12),    # tighter is better
    },
    "ASSEMBLY": {
        "winding_tension_n":      (13.5, 16.5),    # nominal 15 +/- 1.5
        "weld_strength_n":        (160.0, 200.0),  # nominal 180 +/- 20
        "initial_resistance_mohm":(10.0, 14.0),    # nominal 12 +/- 2
    },
    "ELECTROLYTE_FILL": {
        "electrolyte_volume_ml":  (14.4, 15.6),    # nominal 15 +/- 0.6
        "seal_pressure_psi":      (108.0, 132.0),  # nominal 120 +/- 12
    },
    "FORMATION": {
        "first_cycle_capacity_ah":(14.0, 16.0),    # nominal 15 +/- 1
    },
}


def out_of_spec_count(stage: str, measurements: dict) -> int:
    """Count how many measurements at this stage are outside their spec range."""
    specs = STAGE_SPECS.get(stage, {})
    count = 0
    for key, (lo, hi) in specs.items():
        v = measurements.get(key)
        if v is None:
            continue
        if v < lo or v > hi:
            count += 1
    return count
