"""
Step 4 - train the WTP estimator + the conversion classifier.

    python -m model.train              # full run, writes artifacts + plots
    python -m model.train --fast       # fewer rounds, skip SHAP plot

Artifacts written to model/artifacts/:
  wtp_estimator.joblib        {model, category_maps, features, metadata}
  conversion_classifier.joblib {model, category_maps, features, metadata}
  metrics.json                MAE / RMSE / R2 (wtp) + AUC / logloss (conv)
  training_report.txt         human-readable summary

Docs plots written to docs/:
  feature_importance_wtp.png, shap_summary_wtp.png,
  wtp_distribution_by_segment.png, conversion_lift_curve.png
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)

from . import schema as S
from .dataset import make_split
from . import plots

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
DOCS = Path(__file__).resolve().parents[1] / "docs"


# --------------------------------------------------------------------------- #
def _cat_idx(feature_cols: list[str]) -> list[int]:
    return [feature_cols.index(c) for c in S.CATEGORICALS if c in feature_cols]


def train_wtp(fast: bool = False) -> dict:
    print("\n=== WTP estimator (regression on actual_wtp) ===")
    sp = make_split(S.WTP_TARGET)
    feat = list(sp.X_train.columns)
    cat_idx = _cat_idx(feat)

    dtrain = lgb.Dataset(sp.X_train, sp.y_train, categorical_feature=cat_idx, free_raw_data=False)
    dval = lgb.Dataset(sp.X_val, sp.y_val, reference=dtrain, categorical_feature=cat_idx,
                       free_raw_data=False)

    params = {
        "objective": "regression",
        "metric": ["l1", "rmse"],
        "learning_rate": 0.03 if not fast else 0.1,
        "num_leaves": 63,
        "feature_fraction": 0.85,
        "bagging_fraction": 0.85,
        "bagging_freq": 1,
        "min_data_in_leaf": 40,
        "lambda_l2": 1.0,
        "verbose": -1,
        "seed": 42,
    }
    rounds = 300 if fast else 2000
    model = lgb.train(
        params, dtrain, num_boost_round=rounds, valid_sets=[dtrain, dval],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(120, verbose=False), lgb.log_evaluation(200)],
    )

    # ---- evaluate on the untouched test split ----
    pred = model.predict(sp.X_test, num_iteration=model.best_iteration)
    mae = mean_absolute_error(sp.y_test, pred)
    rmse = float(np.sqrt(mean_squared_error(sp.y_test, pred)))
    r2 = r2_score(sp.y_test, pred)
    # baseline = predict the global mean
    base_mae = mean_absolute_error(sp.y_test, np.full_like(pred, sp.y_train.mean()))
    print(f"  test  MAE={mae:.5f}  RMSE={rmse:.5f}  R2={r2:.4f}   (mean-baseline MAE={base_mae:.5f})")

    # ---- SHAP explainer built once, stored with the model ----
    import shap

    explainer = shap.TreeExplainer(model)

    # ---- lightweight distribution stats for the confidence heuristic ----
    feature_stats = {
        "numeric_p01": {c: float(sp.X_train[c].quantile(0.01)) for c in S.NUMERICS if c in feat},
        "numeric_p99": {c: float(sp.X_train[c].quantile(0.99)) for c in S.NUMERICS if c in feat},
        "target_p05": float(sp.y_train.quantile(0.05)),
        "target_p95": float(sp.y_train.quantile(0.95)),
        "target_mean": float(sp.y_train.mean()),
        "test_residual_std": float(np.std(sp.y_test.to_numpy() - pred)),
    }

    bundle = {
        "model": model,
        "explainer": explainer,
        "category_maps": sp.category_maps,
        "features": feat,
        "categorical_features": S.CATEGORICALS,
        "feature_stats": feature_stats,
        "best_iteration": model.best_iteration,
        "metadata": {
            "kind": "wtp_estimator",
            "target": S.WTP_TARGET,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "n_train": int(len(sp.X_train)),
            "n_val": int(len(sp.X_val)),
            "n_test": int(len(sp.X_test)),
            "test_mae": mae, "test_rmse": rmse, "test_r2": r2,
            "baseline_mae": base_mae,
        },
    }
    out = ARTIFACTS / "wtp_estimator.joblib"
    joblib.dump(bundle, out, compress=3)
    sz = out.stat().st_size / 1e6
    print(f"  saved {out}  ({sz:.1f} MB)")

    # ---- load+infer timing check (<50ms requirement) ----
    _timing_check(out, sp.X_test.iloc[[0]])

    # ---- plots ----
    plots.feature_importance(model, feat)
    if not fast:
        sample = sp.X_test.sample(min(2000, len(sp.X_test)), random_state=0)
        sv = explainer.shap_values(sample)
        plots.shap_summary(sv, sample)
    seg_df = sp.raw_test.copy()
    seg_df["pred_wtp"] = pred
    plots.wtp_distribution_by_segment(seg_df)

    return bundle["metadata"]


def train_conversion(fast: bool = False) -> dict:
    print("\n=== Conversion classifier (list price vs adjusted price) ===")
    sp = make_split(S.CONVERSION_TARGET, extra_features=[S.CONVERSION_EXTRA])
    feat = list(sp.X_train.columns)
    cat_idx = _cat_idx(feat)

    dtrain = lgb.Dataset(sp.X_train, sp.y_train, categorical_feature=cat_idx, free_raw_data=False)
    dval = lgb.Dataset(sp.X_val, sp.y_val, reference=dtrain, categorical_feature=cat_idx,
                       free_raw_data=False)
    params = {
        "objective": "binary",
        "metric": ["auc", "binary_logloss"],
        "learning_rate": 0.03 if not fast else 0.1,
        "num_leaves": 63,
        "feature_fraction": 0.85,
        "bagging_fraction": 0.85,
        "bagging_freq": 1,
        "min_data_in_leaf": 40,
        "lambda_l2": 1.0,
        "verbose": -1,
        "seed": 42,
    }
    rounds = 300 if fast else 1500
    model = lgb.train(
        params, dtrain, num_boost_round=rounds, valid_sets=[dtrain, dval],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(120, verbose=False), lgb.log_evaluation(200)],
    )
    proba = model.predict(sp.X_test, num_iteration=model.best_iteration)
    auc = roc_auc_score(sp.y_test, proba)
    ll = log_loss(sp.y_test, proba)
    print(f"  test  AUC={auc:.4f}  logloss={ll:.4f}")

    bundle = {
        "model": model,
        "category_maps": sp.category_maps,
        "features": feat,
        "categorical_features": S.CATEGORICALS,
        "price_feature": S.CONVERSION_EXTRA,
        "best_iteration": model.best_iteration,
        "metadata": {
            "kind": "conversion_classifier",
            "target": S.CONVERSION_TARGET,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "test_auc": auc, "test_logloss": ll,
        },
    }
    out = ARTIFACTS / "conversion_classifier.joblib"
    joblib.dump(bundle, out, compress=3)
    print(f"  saved {out}  ({out.stat().st_size/1e6:.1f} MB)")

    # conversion-lift curve uses the raw test frame
    plots.conversion_lift_curve(sp.raw_test)
    return bundle["metadata"]


def _timing_check(path: Path, one_row: pd.DataFrame) -> None:
    t0 = time.perf_counter()
    b = joblib.load(path)
    load_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    b["model"].predict(one_row, num_iteration=b["best_iteration"])
    _ = b["explainer"].shap_values(one_row)
    infer_ms = (time.perf_counter() - t1) * 1000
    print(f"  timing: load={load_ms:.1f}ms  predict+shap(1 row)={infer_ms:.1f}ms "
          f"({'OK <50ms' if infer_ms < 50 else 'SLOW'})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="quick run, skip SHAP beeswarm")
    args = ap.parse_args()

    t0 = time.time()
    wtp_meta = train_wtp(fast=args.fast)
    conv_meta = train_conversion(fast=args.fast)

    metrics = {"wtp_estimator": wtp_meta, "conversion_classifier": conv_meta}
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

    report = [
        "WTP Dynamic Pricing Engine - training report",
        f"generated: {datetime.now(timezone.utc).isoformat()}",
        f"wall time: {time.time()-t0:.1f}s",
        "",
        "WTP estimator (regression):",
        f"  MAE  = {wtp_meta['test_mae']:.5f}",
        f"  RMSE = {wtp_meta['test_rmse']:.5f}",
        f"  R2   = {wtp_meta['test_r2']:.4f}",
        f"  mean-baseline MAE = {wtp_meta['baseline_mae']:.5f}",
        "",
        "Conversion classifier (binary):",
        f"  AUC     = {conv_meta['test_auc']:.4f}",
        f"  logloss = {conv_meta['test_logloss']:.4f}",
        "",
        "Artifacts: model/artifacts/{wtp_estimator,conversion_classifier}.joblib",
        "Plots:     docs/{feature_importance_wtp,shap_summary_wtp,"
        "wtp_distribution_by_segment,conversion_lift_curve}.png",
    ]
    (ARTIFACTS / "training_report.txt").write_text("\n".join(report))
    print("\n" + "\n".join(report))


if __name__ == "__main__":
    main()
