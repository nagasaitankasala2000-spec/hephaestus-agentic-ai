"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — Yield Predictor (inference wrapper)                     ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Loads the trained XGBoost model once at import time. Exposes a clean    ║
║  predict() method that FORGE calls for every cell exiting Coating.       ║
║                                                                           ║
║  Latency: ~2 ms per prediction (in-process, no network overhead).        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import pickle
import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np

# Make sure parent directory is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.synthetic_data import FEATURES

logger = logging.getLogger("hephaestus.yield_predictor")

MODEL_PATH = Path(__file__).parent / "models" / "yield_model.pkl"


class YieldPredictor:
    """
    Wraps the trained XGBoost yield prediction model.

    Usage:
        from ml.yield_predictor import predictor
        prob = predictor.predict({
            "coating_thickness_um": 78.5,
            "coating_uniformity_cv": 1.0,
            ...
        })
        if prob > 0.70:
            # cell flagged as high-risk
    """

    def __init__(self, model_path: Path = MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self.feature_names = FEATURES
        self.predictions_made = 0
        self.high_risk_flagged = 0
        self._load_model()

    def _load_model(self) -> None:
        """Load the pickled XGBoost model from disk."""
        if not self.model_path.exists():
            logger.warning(
                f"Model file not found at {self.model_path}. "
                f"Run `python ml/train_yield_model.py` first. "
                f"Predictor will return 0.0 until model is available."
            )
            return
        try:
            with open(self.model_path, "rb") as f:
                self.model = pickle.load(f)
            logger.info(f"✅ Yield model loaded from {self.model_path}")
        except Exception as e:
            logger.exception(f"Failed to load yield model: {e}")
            self.model = None

    def is_ready(self) -> bool:
        """True if the model is loaded and ready to make predictions."""
        return self.model is not None

    def predict(self, measurements: Dict[str, float]) -> float:
        """
        Predict probability of QC failure for a cell.

        Args:
            measurements: dict of feature_name → value. Missing features are
                          filled with reasonable defaults (target nominal value).

        Returns:
            Probability of failure, 0.0 to 1.0.
        """
        if self.model is None:
            return 0.0

        # Build feature vector in the order the model expects.
        # The simulator emits short keys (e.g. "thickness_um"); the model
        # expects stage-prefixed keys (e.g. "coating_thickness_um").
        # This map bridges the two schemas.
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
        # Normalize incoming measurements to model feature names
        normalized = {}
        for key, value in measurements.items():
            mapped = SIM_TO_MODEL_KEY.get(key, key)
            normalized[mapped] = value

        # Fill missing features with sensible defaults (target nominal values)
        defaults = {
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
        feature_vector = np.array([[
            normalized.get(f, defaults[f]) for f in self.feature_names
        ]])

        try:
            probability = float(self.model.predict_proba(feature_vector)[0, 1])
        except Exception as e:
            logger.exception(f"Prediction failed: {e}")
            return 0.0

        self.predictions_made += 1
        if probability > 0.70:
            self.high_risk_flagged += 1

        return probability

    def stats(self) -> dict:
        """Runtime statistics for diagnostics."""
        return {
            "model_loaded": self.is_ready(),
            "model_path": str(self.model_path),
            "predictions_made": self.predictions_made,
            "high_risk_flagged": self.high_risk_flagged,
            "high_risk_rate_pct": (
                100.0 * self.high_risk_flagged / max(self.predictions_made, 1)
            ),
        }


# Module-level singleton — loads once when imported.
predictor = YieldPredictor()
