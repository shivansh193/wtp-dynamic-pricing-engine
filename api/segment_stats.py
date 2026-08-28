"""
Posterior over a segment's WTP multiplier.

Framing: the observations are the WTP *estimator's predictions* for past
shoppers in this segment, not realised willingness-to-pay (unobservable without
a controlled price experiment). So this is a posterior over "what the model
outputs for this segment", with sampling uncertainty - useful for showing how
tight the pricing is per segment, not a causal WTP.

Model: conjugate Normal for the segment mean with a *weak* prior, so once a
handful of decisions exist the data dominates:

    prior     mu ~ N(m0 = 1.00, tau0 = 0.15)          (tau0 = prior SD of the mean)
    data      x_i ~ N(mu, sigma^2),  sigma = max(sample SD, SIGMA_FLOOR)
    posterior mu | data ~ N(m_n, s_n^2)
        prec_n = 1/tau0^2 + n/sigma^2
        m_n    = (m0/tau0^2 + sum x_i / sigma^2) / prec_n
        s_n^2  = 1 / prec_n

Because sigma is estimated from the same n points, the 95% interval widens it to
a **Student-t** interval with (n - 1) dof (falls back to the normal 1.96 for
n < 2 or when SciPy is unavailable), and is **clipped to [0.85, 1.25]** since
WTP is truncated at the price band.
"""

from __future__ import annotations

import json
import math
from typing import Any

PRIOR_MEAN = 1.00
PRIOR_SD = 0.15          # weak - ~8-10 decisions outweigh it
SIGMA_FLOOR = 0.015      # guards against overconfidence when predictions cluster
WTP_MIN, WTP_MAX = 0.85, 1.25

try:
    from scipy.stats import t as _student_t  # type: ignore

    _HAVE_SCIPY = True
except Exception:  # noqa: BLE001
    _HAVE_SCIPY = False


def _signals(row: dict) -> dict:
    v = row.get("input_signals")
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return {}
    return v or {}


def _key(sig: dict) -> str:
    return "|".join(str(sig.get(k, "?")) for k in
                    ("city_tier", "device_type", "payment_method_preference"))


def _crit(dof: float) -> float:
    if _HAVE_SCIPY and dof >= 1:
        return float(_student_t.ppf(0.975, dof))
    return 1.959964


def posterior(segment_key: str, decision_rows: list[dict]) -> dict[str, Any]:
    xs: list[float] = []
    for r in decision_rows:
        if _key(_signals(r)) == segment_key:
            try:
                xs.append(float(r.get("wtp_score")))
            except (TypeError, ValueError):
                continue

    n = len(xs)
    xbar = sum(xs) / n if n else None
    obs_sd = (
        math.sqrt(sum((x - xbar) ** 2 for x in xs) / (n - 1)) if n > 1 else None
    )

    sigma = max(obs_sd or 0.0, SIGMA_FLOOR)
    prior_prec = 1.0 / PRIOR_SD ** 2
    like_prec = n / sigma ** 2 if n else 0.0
    prec_n = prior_prec + like_prec
    m_n = (PRIOR_MEAN * prior_prec + (sum(xs) / sigma ** 2 if n else 0.0)) / prec_n
    s_n = math.sqrt(1.0 / prec_n)

    dof = max(n - 1, 1)
    crit = _crit(dof)
    ci_lo = max(WTP_MIN, m_n - crit * s_n)
    ci_hi = min(WTP_MAX, m_n + crit * s_n)

    # spread of a single new shopper's predicted WTP (not the mean) in this segment
    pred_sd = math.sqrt(sigma ** 2 + s_n ** 2)

    # segment conversion-probability curve. NOTE: this uses the logistic
    # price-response shape the synthetic generator was built with; with real
    # data it comes from the fitted (and calibrated) conversion classifier.
    curve = []
    for m in [0.90, 0.95, 1.00, 1.05, 1.10, 1.15]:
        p = 1.0 / (1.0 + math.exp(-8.5 * (m_n - m)))
        curve.append({"price_multiplier": m, "conversion_probability": round(p, 4)})

    return {
        "segment_key": segment_key,
        "n_observations": n,
        "measures": "model-predicted WTP multiplier (not realised WTP)",
        "prior": {"mean": PRIOR_MEAN, "sd": PRIOR_SD},
        "observed": {
            "mean_wtp": round(xbar, 5) if xbar is not None else None,
            "sd_wtp": round(obs_sd, 5) if obs_sd is not None else None,
        },
        "posterior": {
            "mean_wtp": round(m_n, 5),
            "sd": round(s_n, 5),
            "dof": dof,
            "ci_95": [round(ci_lo, 5), round(ci_hi, 5)],
            "ci_method": "student-t" if (_HAVE_SCIPY and n > 1) else "normal-approx",
            "ci_clipped_to_price_band": [WTP_MIN, WTP_MAX],
            "predictive_sd_single_shopper": round(pred_sd, 5),
        },
        "conversion_curve": curve,
    }
