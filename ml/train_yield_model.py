"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HEPHAESTUS v2 — Yield Prediction Model Trainer                          ║
║  ────────────────────────────────────────────────────────────────────    ║
║  Trains an XGBoost classifier to predict cell QC failure from process    ║
║  measurements captured at stages 2-6 (before Formation, the bottleneck). ║
║                                                                           ║
║  Run once. Output is ml/models/yield_model.pkl, loaded by FORGE at boot. ║
║                                                                           ║
║  Why XGBoost:                                                             ║
║    • Best-in-class for tabular data with ~10K samples and ~14 features  ║
║    • No feature scaling needed (trees are scale-invariant)              ║
║    • Native handling of class imbalance via scale_pos_weight            ║
║    • Built-in feature importance for interpretability                   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pickle
import csv
from pathlib import Path
from typing import Tuple, List

import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    roc_auc_score,
)

from ml.synthetic_data import FEATURES, TARGET


TRAINING_DATA_PATH = "ml/training_data.csv"
MODEL_OUTPUT_PATH = "ml/models/yield_model.pkl"


# ════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ════════════════════════════════════════════════════════════════════════

def load_dataset(path: str = TRAINING_DATA_PATH) -> Tuple[np.ndarray, np.ndarray]:
    """Load CSV and return X (features) and y (target) as numpy arrays."""
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: float(v) for k, v in row.items()})

    if not rows:
        raise FileNotFoundError(
            f"No data found at {path}. Run `python ml/synthetic_data.py` first."
        )

    X = np.array([[row[f] for f in FEATURES] for row in rows])
    y = np.array([row[TARGET] for row in rows], dtype=int)
    print(f"Loaded {len(rows):,} samples with {X.shape[1]} features.")
    return X, y


# ════════════════════════════════════════════════════════════════════════
# TRAINING
# ════════════════════════════════════════════════════════════════════════

def train_model(X_train, y_train) -> xgb.XGBClassifier:
    """Train the XGBoost classifier on training data."""
    # Class imbalance: failures are ~7% of data → weight them higher
    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    scale_pos_weight = n_neg / max(n_pos, 1)
    print(f"Class balance: {n_neg:,} pass, {n_pos:,} fail "
          f"(scale_pos_weight={scale_pos_weight:.2f})")

    model = xgb.XGBClassifier(
        n_estimators=200,        # 200 trees — good balance of fit vs. overfit
        max_depth=6,             # moderate depth — prevents overfitting
        learning_rate=0.1,       # standard
        scale_pos_weight=scale_pos_weight,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,               # use all CPU cores
    )
    model.fit(X_train, y_train)
    return model


# ════════════════════════════════════════════════════════════════════════
# EVALUATION
# ════════════════════════════════════════════════════════════════════════

def evaluate(model: xgb.XGBClassifier, X_test, y_test) -> None:
    """Print evaluation metrics on held-out test set."""
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    auc = roc_auc_score(y_test, y_pred_proba)
    cm = confusion_matrix(y_test, y_pred)

    print()
    print("═══════════════════════════════════════════════════════")
    print("  MODEL EVALUATION — held-out test set (never seen)    ")
    print("═══════════════════════════════════════════════════════")
    print(f"  Accuracy:       {acc:.4f}    (raw % correct)")
    print(f"  Precision:      {prec:.4f}    (when model says 'fail', how often right)")
    print(f"  Recall:         {rec:.4f}    (of actual failures, how many caught)")
    print(f"  F1 score:       {f1:.4f}    (harmonic mean of precision/recall)")
    print(f"  ROC AUC:        {auc:.4f}    (threshold-independent quality)")
    print()
    print("  Confusion matrix:")
    print(f"                       Predicted PASS    Predicted FAIL")
    print(f"    Actual PASS:    {cm[0][0]:>10,}        {cm[0][1]:>10,}")
    print(f"    Actual FAIL:    {cm[1][0]:>10,}        {cm[1][1]:>10,}")
    print("═══════════════════════════════════════════════════════")
    print()


def print_feature_importance(model: xgb.XGBClassifier) -> None:
    """Which features does the model think matter most?"""
    importances = list(zip(FEATURES, model.feature_importances_))
    importances.sort(key=lambda x: x[1], reverse=True)
    print("Top features by importance:")
    for name, score in importances[:8]:
        bar = "█" * int(score * 80)
        print(f"  {name:<30} {score:.4f}  {bar}")
    print()


# ════════════════════════════════════════════════════════════════════════
# PERSISTENCE
# ════════════════════════════════════════════════════════════════════════

def save_model(model: xgb.XGBClassifier, path: str = MODEL_OUTPUT_PATH) -> None:
    """Pickle the trained model to disk."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model, f)
    size_kb = Path(path).stat().st_size / 1024
    print(f"✅ Saved trained model to {path} ({size_kb:.1f} KB)")


# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

def main():
    # 1. Load data
    X, y = load_dataset()

    # 2. Train/test split — 80/20, stratified to preserve class ratio
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"Train: {len(X_train):,} samples | Test: {len(X_test):,} samples")
    print()

    # 3. Train
    print("Training XGBoost classifier...")
    model = train_model(X_train, y_train)
    print("Training complete.")

    # 4. Evaluate
    evaluate(model, X_test, y_test)
    print_feature_importance(model)

    # 5. Save
    save_model(model)


if __name__ == "__main__":
    main()
