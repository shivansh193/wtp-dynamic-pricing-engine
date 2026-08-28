# model - WTP Estimator

Two LightGBM models plus SHAP explainability.

| artifact | task | metric (test split) |
|---|---|---|
| `artifacts/wtp_estimator.joblib` | regression on `actual_wtp` (0.85–1.25) | MAE ≈ 0.021, RMSE ≈ 0.026, **R² ≈ 0.91** (mean-baseline MAE ≈ 0.070) |
| `artifacts/conversion_classifier.joblib` | P(convert) given an **offered price multiplier** (list vs adjusted) | AUC ≈ 0.72, logloss ≈ 0.60 |

## Train

```bash
python -m model.train           # ~15s, writes artifacts + 4 docs plots
python -m model.train --fast     # quicker, skips the SHAP beeswarm
```

Requires `data/processed/transactions.csv` (run the data pipeline first).

## Design

- **Split**: deterministic 70/15/15 by row hash — reproducible without an index file.
- **Categoricals**: native LightGBM categorical handling; the
  `{value → int code}` maps are frozen at train time and stored inside the
  joblib bundle so inference encodes identically. Unseen values → `-1`.
- **SHAP**: a `shap.TreeExplainer` is built once and **serialized with the
  model**, so per-request explanations need no rebuild. `predict()` returns
  the signed contribution of every feature for that single row.
- **Confidence** (`high` / `medium` / `low`): a GBM has no native predictive
  interval, so `inference.py` uses an explainable heuristic — unseen category
  levels, numeric extrapolation beyond the training p01–p99, prediction pinned
  to a price-cap bound, or near-zero SHAP signal each dock the score.
- **Latency**: load ≈ 20–30 ms, `predict + SHAP` for one row ≈ 3–8 ms — well
  under the 50 ms budget (asserted in `train.py`'s timing check).

## Inference

```python
from model.inference import get_model
m = get_model()                                   # process-wide singleton
out = m.predict(customer_signals_dict)            # wtp_multiplier, shap_top, confidence
curve = m.conversion_curve(signals, list_price=4999)   # P(convert) at 0.90 … 1.15
```

## Docs plots (written to `/docs`)

- `feature_importance_wtp.png` — LightGBM gain importance
- `shap_summary_wtp.png` — SHAP beeswarm over a 2 000-row test sample
- `wtp_distribution_by_segment.png` — WTP boxplots by tier / device / payment
- `conversion_lift_curve.png` — conversion rate vs (WTP − offered price)
