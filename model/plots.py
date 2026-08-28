"""
Docs artefacts (Buildathon Step 4 deliverables), written to /docs:

  feature_importance_wtp.png     LightGBM gain importance, WTP model
  shap_summary_wtp.png           SHAP beeswarm over the test set
  wtp_distribution_by_segment.png  actual vs predicted WTP by key segment
  conversion_lift_curve.png      converted-rate vs (wtp - offered price) bucket

matplotlib only, no seaborn. All plots are theme-neutral (white bg) so they
embed cleanly in the PDF writeup.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
DOCS.mkdir(parents=True, exist_ok=True)


def feature_importance(model, feature_names, out=DOCS / "feature_importance_wtp.png"):
    imp = model.feature_importance(importance_type="gain")
    order = np.argsort(imp)[::-1]
    names = [feature_names[i] for i in order]
    vals = imp[order]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(names[::-1], vals[::-1], color="#2563eb")
    ax.set_title("WTP estimator - feature importance (LightGBM gain)")
    ax.set_xlabel("gain")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def shap_summary(shap_values, X_sample, out=DOCS / "shap_summary_wtp.png"):
    import shap

    fig = plt.figure(figsize=(8, 6))
    shap.summary_plot(shap_values, X_sample, show=False, plot_size=None)
    plt.title("WTP estimator - SHAP summary (test sample)")
    plt.tight_layout()
    plt.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


def wtp_distribution_by_segment(df: pd.DataFrame, pred_col="pred_wtp",
                                out=DOCS / "wtp_distribution_by_segment.png"):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    segs = [
        ("city_tier", [1, 2, 3]),
        ("device_type", ["Android_budget", "Android_premium", "iPhone", "Desktop"]),
        ("payment_method_preference", ["COD", "Debit_Card", "UPI", "Wallet", "Credit_Card"]),
    ]
    for ax, (col, order) in zip(axes, segs):
        data = [df.loc[df[col] == lvl, "actual_wtp"].values for lvl in order]
        ax.boxplot(data, labels=[str(o) for o in order], showfliers=False)
        ax.set_title(f"actual WTP by {col}")
        ax.tick_params(axis="x", rotation=30)
        ax.axhline(1.0, color="#888", ls="--", lw=1)
    axes[0].set_ylabel("WTP multiplier")
    fig.suptitle("WTP distribution by segment")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def conversion_lift_curve(df: pd.DataFrame, out=DOCS / "conversion_lift_curve.png"):
    """Converted-rate as a function of how far the offered price sits below WTP."""
    g = df.copy()
    g["gap"] = g["actual_wtp"] - g["offered_price_multiplier"]
    bins = np.linspace(-0.2, 0.25, 19)
    g["bucket"] = pd.cut(g["gap"], bins)
    curve = g.groupby("bucket", observed=True)["converted"].mean()
    centers = [iv.mid for iv in curve.index]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(centers, curve.values, marker="o", color="#059669")
    ax.axvline(0.0, color="#888", ls="--", lw=1, label="offered price = WTP")
    ax.set_xlabel("WTP multiplier  -  offered price multiplier   (>0 = underpriced)")
    ax.set_ylabel("conversion rate")
    ax.set_title("Conversion lift curve - pricing below WTP lifts conversion")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out
