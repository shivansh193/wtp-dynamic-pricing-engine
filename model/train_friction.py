"""
Friction classifier training (Friction-Aware Conversion Engine, Step 1).

    python -m model.train_friction [--fast]

1. Load the synthetic transactions.
2. Assign a friction label to each row with the rule scorer in
   api/friction_engine.py (argmax of the six friction scores).
3. Inject ~15% label noise (flip to a random other class) to simulate the
   real-world ambiguity a pure-rule system would never see.
4. Train a LightGBM multiclass classifier on the same feature space as the WTP
   model plus a few friction-relevant derivations (wtp_norm, is_new_account).
5. SHAP TreeExplainer for per-prediction attributions.
6. Save model/artifacts/friction_classifier.joblib + docs/friction_importance.png.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.friction_engine import (  # noqa: E402
    FRICTION_TYPES,
    FrictionContext,
    _wtp_norm,
    rule_scores,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "model" / "artifacts"
DOCS = ROOT / "docs"
DATA = ROOT / "data" / "processed" / "transactions.csv"

CAT_FEATURES = [
    "device_type", "city_tier", "income_tier", "payment_method_preference",
    "time_of_day", "day_of_week", "referral_source", "ip_type", "product_category",
]
NUM_FEATURES = [
    "digital_demand_index", "ip_trust_multiplier", "historical_aov", "return_rate",
    "payment_success_rate", "cod_completion_rate", "cross_merchant_trust_score",
    "num_merchants_transacted", "account_age_days", "cart_value",
    "is_festival_period", "festival_intensity",
]
DERIVED = ["wtp_multiplier", "wtp_norm", "is_new_account"]
FEATURES = CAT_FEATURES + NUM_FEATURES + DERIVED
_LGBM_THREADS = int(__import__("os").getenv("LGBM_NUM_THREADS",
                    __import__("os").getenv("OMP_NUM_THREADS", "0")) or 0)


def _rule_label(row: pd.Series) -> str:
    sig = row.to_dict()
    # a light session-context guess so decision_paralysis / delivery_anxiety can fire
    ctx = FrictionContext(
        cart_abandonment_rate=float(np.clip((row["return_rate"] * 0.6 +
                                             (1 - row["payment_success_rate"]) * 0.8), 0, 1)),
        repeat_sessions_on_product=int(row["num_merchants_transacted"] > 8) +
        int(abs(row["actual_wtp"] - 1.0) < 0.03),
        first_purchase_in_category=bool(row["num_merchants_transacted"] <= 2 and
                                        row["product_category"] in ("electronics", "home")),
        session_minutes=0.0,
        cod_eligible=bool(row["cross_merchant_trust_score"] > 55 and
                          row["cod_completion_rate"] > 0.8),
    )
    s = rule_scores(sig, float(row["actual_wtp"]), ctx)
    return max(s, key=s.get)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()

    if not DATA.exists():
        raise SystemExit(f"{DATA} missing — run the data pipeline first.")
    df = pd.read_csv(DATA)
    rng = np.random.default_rng(42)

    print(f"labelling {len(df):,} rows with the rule scorer…")
    df["friction"] = df.apply(_rule_label, axis=1)
    base_dist = df["friction"].value_counts(normalize=True).round(3).to_dict()
    print("  rule label distribution:", base_dist)

    # ---- 15% label noise ----
    noise_mask = rng.random(len(df)) < 0.15
    others = {t: [x for x in FRICTION_TYPES if x != t] for t in FRICTION_TYPES}
    df.loc[noise_mask, "friction"] = [
        rng.choice(others[t]) for t in df.loc[noise_mask, "friction"]
    ]
    print(f"  injected noise on {int(noise_mask.sum()):,} rows")

    # ---- features ----
    df["wtp_multiplier"] = df["actual_wtp"]
    df["wtp_norm"] = df["actual_wtp"].map(_wtp_norm)
    df["is_new_account"] = (df["account_age_days"] < 90).astype(int)

    X = df[FEATURES].copy()
    category_maps: dict[str, dict] = {}
    for c in CAT_FEATURES:
        cats = sorted(X[c].astype(str).unique().tolist())
        category_maps[c] = {v: i for i, v in enumerate(cats)}
        X[c] = X[c].astype(str).map(category_maps[c]).astype("int64")
    X = X.apply(pd.to_numeric, errors="coerce")

    classes = FRICTION_TYPES
    y = df["friction"].map({c: i for i, c in enumerate(classes)}).astype(int)

    n = len(df)
    idx = rng.permutation(n)
    cut1, cut2 = int(n * 0.7), int(n * 0.85)
    tr, va, te = idx[:cut1], idx[cut1:cut2], idx[cut2:]
    cat_idx = [FEATURES.index(c) for c in CAT_FEATURES]

    # inverse-frequency sample weights so the rare-but-important frictions
    # (trust_deficit, payment_friction) are actually learned, not ignored
    freq = y.iloc[tr].value_counts().sort_index()
    w_by_class = (len(tr) / (len(classes) * freq)).clip(upper=8.0)
    w_tr = y.iloc[tr].map(w_by_class).to_numpy()

    dtr = lgb.Dataset(X.iloc[tr], y.iloc[tr], weight=w_tr,
                      categorical_feature=cat_idx, free_raw_data=False)
    dva = lgb.Dataset(X.iloc[va], y.iloc[va], reference=dtr, categorical_feature=cat_idx,
                      free_raw_data=False)
    params = {
        "objective": "multiclass", "num_class": len(classes), "metric": "multi_logloss",
        "learning_rate": 0.05 if not args.fast else 0.12, "num_leaves": 47,
        "feature_fraction": 0.85, "bagging_fraction": 0.85, "bagging_freq": 1,
        "min_data_in_leaf": 60, "lambda_l2": 1.0, "verbose": -1, "seed": 42,
        "num_threads": _LGBM_THREADS, "force_col_wise": True,
    }
    rounds = 250 if args.fast else 900
    model = lgb.train(params, dtr, num_boost_round=rounds, valid_sets=[dva],
                      valid_names=["val"],
                      callbacks=[lgb.early_stopping(80, verbose=False),
                                 lgb.log_evaluation(150)])

    proba_te = model.predict(X.iloc[te], num_iteration=model.best_iteration)
    pred_te = proba_te.argmax(1)
    acc = accuracy_score(y.iloc[te], pred_te)
    f1 = f1_score(y.iloc[te], pred_te, average="macro")
    # agreement with the *clean* rule label (before noise) on held-out rows
    clean = df.iloc[te].apply(_rule_label, axis=1).map({c: i for i, c in enumerate(classes)})
    rule_agree = accuracy_score(clean, pred_te)
    print(f"  test  accuracy={acc:.3f}  macro-F1={f1:.3f}  agreement-with-rules={rule_agree:.3f}")

    explainer = None
    try:
        import shap

        explainer = shap.TreeExplainer(model)
    except Exception as exc:  # noqa: BLE001
        print(f"  SHAP explainer skipped: {exc!r}")

    bundle = {
        "model": model,
        "explainer": explainer,
        "features": FEATURES,
        "categorical_features": CAT_FEATURES,
        "category_maps": category_maps,
        "classes": classes,
        "metadata": {
            "kind": "friction_classifier",
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "test_accuracy": acc, "test_macro_f1": f1, "rule_agreement": rule_agree,
            "label_noise": 0.15, "rule_label_distribution": base_dist,
        },
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / "friction_classifier.joblib"
    joblib.dump(bundle, out, compress=3)
    print(f"  saved {out} ({out.stat().st_size/1e6:.1f} MB)")

    (ARTIFACTS / "friction_metrics.json").write_text(json.dumps(bundle["metadata"], indent=2, default=str))

    # feature importance plot
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        imp = model.feature_importance(importance_type="gain")
        order = np.argsort(imp)[::-1][:15]
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.barh([FEATURES[i] for i in order][::-1], imp[order][::-1], color="#4f46e5")
        ax.set_title("Friction classifier — feature importance (gain)")
        fig.tight_layout()
        DOCS.mkdir(parents=True, exist_ok=True)
        fig.savefig(DOCS / "friction_importance.png", dpi=130)
        plt.close(fig)
        print(f"  wrote {DOCS / 'friction_importance.png'}")
    except Exception as exc:  # noqa: BLE001
        print(f"  importance plot skipped: {exc!r}")


if __name__ == "__main__":
    main()
