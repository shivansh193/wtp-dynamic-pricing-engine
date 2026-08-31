"""
Inference wrapper used by the pricing API.

    m = get_model()                     # process-wide singleton, warm
    out = m.predict(raw_signals)        # dict: wtp, shap_top, confidence, ...
    conv = m.conversion_curve(raw_signals, list_price=4999)

Guarantees:
  - load() completes in well under the 50ms budget (measured at train time)
  - predict() = LightGBM predict + TreeExplainer SHAP for ONE row, ~1-5ms
  - never raises to the caller: on any failure returns a safe neutral result
    with confidence="low"
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import schema as S

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


class WTPModel:
    def __init__(self, wtp_bundle: dict, conv_bundle: dict | None):
        self._wtp = wtp_bundle
        self._conv = conv_bundle
        self._wtp_model = wtp_bundle["model"]
        self._explainer = wtp_bundle["explainer"]
        self._features = wtp_bundle["features"]
        self._cat_maps = wtp_bundle["category_maps"]
        self._stats = wtp_bundle.get("feature_stats", {})
        self._best_it = wtp_bundle.get("best_iteration")

    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, artifacts: Path = ARTIFACTS) -> "WTPModel":
        import joblib

        t0 = time.perf_counter()
        wtp = joblib.load(artifacts / "wtp_estimator.joblib")
        conv = None
        conv_path = artifacts / "conversion_classifier.joblib"
        if conv_path.exists():
            conv = joblib.load(conv_path)
        dt = (time.perf_counter() - t0) * 1000
        print(f"[model] loaded artifacts in {dt:.1f}ms "
              f"(wtp R2={wtp['metadata'].get('test_r2'):.3f})")
        return cls(wtp, conv)

    # ------------------------------------------------------------------ #
    def _encode(self, raw: dict, *, columns: list[str] | None = None,
                extra: dict[str, float] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (encoded_frame_in_column_order, raw_pre_encode_frame)."""
        frame = S.build_features(raw)              # human-readable values
        enc = S.encode(frame, self._cat_maps)     # integer-coded categoricals
        for k, v in (extra or {}).items():
            enc[k] = float(v)
            frame[k] = float(v)
        cols = list(columns or self._features)
        for c in cols:
            if c not in enc.columns:
                enc[c] = 0.0
                frame[c] = 0.0
        return enc[cols], frame

    # ------------------------------------------------------------------ #
    def predict(self, raw: dict) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            X, raw_frame = self._encode(raw)
            wtp = float(self._wtp_model.predict(X, num_iteration=self._best_it)[0])
            wtp = max(0.85, min(1.25, wtp))

            shap_vals = self._explainer.shap_values(X)
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[0]
            contrib = shap_vals[0]
            base = float(getattr(self._explainer, "expected_value", 0.0)
                         if np.ndim(self._explainer.expected_value) == 0
                         else self._explainer.expected_value[0])

            pairs = sorted(
                ({"feature": f, "value": _native(raw_frame.iloc[0][f]), "shap": float(s)}
                 for f, s in zip(self._features, contrib)),
                key=lambda d: abs(d["shap"]), reverse=True,
            )
            confidence, conf_reasons = self._confidence(X, wtp, contrib)
            return {
                "wtp_multiplier": round(wtp, 4),
                "shap_base_value": round(base, 4),
                "shap_top": pairs[:5],
                "shap_all": pairs,
                "confidence": confidence,
                "confidence_reasons": conf_reasons,
                "inference_ms": round((time.perf_counter() - t0) * 1000, 3),
                "degraded": False,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "wtp_multiplier": 1.0,
                "shap_base_value": 1.0,
                "shap_top": [],
                "shap_all": [],
                "confidence": "low",
                "confidence_reasons": [f"inference error: {exc!r}"],
                "inference_ms": round((time.perf_counter() - t0) * 1000, 3),
                "degraded": True,
            }

    # ------------------------------------------------------------------ #
    def wtp_only(self, raw: dict) -> float:
        """WTP multiplier with no SHAP - for bulk simulation (~0.5ms/row vs
        ~3ms for the full predict()). Never raises: returns 1.0 on failure."""
        try:
            X, _ = self._encode(raw)
            wtp = float(self._wtp_model.predict(X, num_iteration=self._best_it)[0])
            return max(0.85, min(1.25, wtp))
        except Exception:  # noqa: BLE001
            return 1.0

    # ------------------------------------------------------------------ #
    def simulate_cohort(self, raws: list[dict], *,
                        cap_up: float = 0.15, cap_down: float = -0.10) -> dict:
        """Vectorised bulk path for the A/B simulator.

        One feature build + one encode for the whole cohort, then three batched
        LightGBM predicts: WTP, conversion at list price (mult=1.0), and
        conversion at each row's capped WTP multiplier. ~1000x cheaper than
        looping predict()/conversion_proba() per shopper.

        Returns numpy arrays: wtp, eff (capped multiplier), conv_list, conv_eff
        (conv_* are None if the conversion classifier artifact is absent).
        """
        df = pd.concat([S.build_features(r) for r in raws], ignore_index=True)
        enc = S.encode(df, self._cat_maps)
        for c in self._features:
            if c not in enc.columns:
                enc[c] = 0.0
        wtp = np.clip(
            self._wtp_model.predict(enc[self._features], num_iteration=self._best_it),
            0.85, 1.25,
        )
        eff = np.clip(wtp, 1.0 + cap_down, 1.0 + cap_up)

        conv_list = conv_eff = None
        if self._conv is not None:
            pf = self._conv["price_feature"]
            cols = list(self._conv["features"])
            Xc = enc.copy()
            for c in cols:
                if c not in Xc.columns and c != pf:
                    Xc[c] = 0.0
            Xc[pf] = 1.0
            Xc = Xc[cols]
            cm, cit = self._conv["model"], self._conv.get("best_iteration")
            conv_list = np.clip(cm.predict(Xc, num_iteration=cit), 1e-3, 1 - 1e-3)
            Xc[pf] = eff
            conv_eff = np.clip(cm.predict(Xc, num_iteration=cit), 1e-3, 1 - 1e-3)

        return {"wtp": wtp, "eff": eff, "conv_list": conv_list, "conv_eff": conv_eff}

    # ------------------------------------------------------------------ #
    def conversion_proba(self, raw: dict, price_multiplier: float) -> float | None:
        if self._conv is None:
            return None
        try:
            pf = self._conv["price_feature"]
            X, _ = self._encode(
                raw, columns=self._conv["features"], extra={pf: float(price_multiplier)}
            )
            return float(self._conv["model"].predict(
                X, num_iteration=self._conv.get("best_iteration"))[0])
        except Exception as exc:  # noqa: BLE001
            print(f"[model] conversion_proba failed: {exc!r}")
            return None

    def conversion_curve(self, raw: dict, list_price: float,
                         multipliers=(0.9, 0.95, 1.0, 1.05, 1.1, 1.15)) -> dict:
        """Conversion probability at list price vs a set of adjusted prices."""
        out = {}
        for m in multipliers:
            p = self.conversion_proba(raw, m)
            out[f"{m:.2f}"] = None if p is None else round(p, 4)
        at_list = out.get("1.00")
        return {
            "at_list_price": at_list,
            "curve": out,
            "list_price": list_price,
        }

    # ------------------------------------------------------------------ #
    def _confidence(self, X: pd.DataFrame, wtp: float, contrib) -> tuple[str, list[str]]:
        """Explainable heuristic (no native uncertainty from a GBM)."""
        reasons: list[str] = []
        score = 2  # 2=high, 1=medium, 0=low

        # unseen categorical levels
        unseen = [c for c in self._wtp["categorical_features"]
                  if c in X.columns and int(X.iloc[0][c]) == -1]
        if unseen:
            score -= 1
            reasons.append(f"unseen category values: {', '.join(unseen)}")

        # numeric extrapolation beyond training p01..p99
        p01 = self._stats.get("numeric_p01", {})
        p99 = self._stats.get("numeric_p99", {})
        oob = []
        for c in p01:
            v = float(X.iloc[0][c])
            if v < p01[c] * 0.9 or v > p99[c] * 1.1:
                oob.append(c)
        if oob:
            score -= 1
            reasons.append(f"inputs outside training range: {', '.join(oob[:4])}")

        # prediction jammed against a clip bound
        if wtp <= 0.855 or wtp >= 1.245:
            reasons.append("prediction at the price-cap boundary")

        # weak signal - SHAP magnitude tiny -> model basically returning the mean
        if float(np.abs(contrib).sum()) < 0.02:
            score -= 1
            reasons.append("weak feature signal (prediction near population mean)")

        label = {2: "high", 1: "medium"}.get(max(score, 0), "low")
        if not reasons:
            reasons.append("all inputs in-distribution, strong feature signal")
        return label, reasons

    # ------------------------------------------------------------------ #
    @property
    def metadata(self) -> dict:
        return {
            "wtp": self._wtp["metadata"],
            "conversion": (self._conv or {}).get("metadata"),
        }


def _native(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4)
    return v


# process-wide singleton
_MODEL: WTPModel | None = None


def get_model() -> WTPModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = WTPModel.load()
    return _MODEL
