"""
Bayesian posterior over a segment's WTP multiplier.

Model: Normal-Normal conjugate with known observation noise.
  prior      mean  mu0 = 1.00   (list price), sd  tau0 = 0.08
  likelihood x_i ~ N(mu, sigma^2),  sigma = max(observed sd, 0.02)
  posterior  mu | data  ~  N(mu_n, tau_n^2)
      tau_n^2 = 1 / (1/tau0^2 + n/sigma^2)
      mu_n    = tau_n^2 * (mu0/tau0^2 + sum(x_i)/sigma^2)

Observations come from the logged pricing decisions whose
(city_tier | device_type | payment_method_preference) equals `segment_key`.
"""

from __future__ import annotations

import json
import math
from typing import Any

PRIOR_MEAN = 1.00
PRIOR_SD = 0.08
MIN_SIGMA = 0.02


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


def posterior(segment_key: str, decision_rows: list[dict]) -> dict[str, Any]:
    xs: list[float] = []
    for r in decision_rows:
        if _key(_signals(r)) == segment_key:
            try:
                xs.append(float(r.get("wtp_score")))
            except (TypeError, ValueError):
                continue

    n = len(xs)
    obs_mean = sum(xs) / n if n else None
    obs_sd = (
        math.sqrt(sum((x - obs_mean) ** 2 for x in xs) / n) if n > 1 else None
    )

    sigma = max(obs_sd or 0.0, MIN_SIGMA)
    prior_prec = 1.0 / (PRIOR_SD ** 2)
    like_prec = n / (sigma ** 2) if n else 0.0
    post_var = 1.0 / (prior_prec + like_prec)
    post_mean = post_var * (PRIOR_MEAN * prior_prec + (sum(xs) / (sigma ** 2) if n else 0.0))
    post_sd = math.sqrt(post_var)

    ci_lo = post_mean - 1.96 * post_sd
    ci_hi = post_mean + 1.96 * post_sd

    # rough conversion-probability curve across price multipliers for this segment
    # (logistic in the gap between the posterior WTP and the offered multiplier)
    curve = []
    for m in [0.90, 0.95, 1.00, 1.05, 1.10, 1.15]:
        gap = post_mean - m
        p = 1.0 / (1.0 + math.exp(-8.5 * gap))
        curve.append({"price_multiplier": m, "conversion_probability": round(p, 4)})

    return {
        "segment_key": segment_key,
        "n_observations": n,
        "prior": {"mean": PRIOR_MEAN, "sd": PRIOR_SD},
        "observed": {
            "mean_wtp": round(obs_mean, 5) if obs_mean is not None else None,
            "sd_wtp": round(obs_sd, 5) if obs_sd is not None else None,
        },
        "posterior": {
            "mean_wtp": round(post_mean, 5),
            "sd": round(post_sd, 5),
            "ci_95": [round(ci_lo, 5), round(ci_hi, 5)],
        },
        "conversion_curve": curve,
    }
