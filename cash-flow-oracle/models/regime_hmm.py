"""
Hidden Markov Model regime detection on daily settlements.

3 hidden states, re-labelled by their fitted mean/volatility into:
  high_season  - above-trend settlements, moderate vol
  low_season   - below-trend settlements, low vol
  stress       - sharp drop and/or elevated vol (chargeback wave, outage)

Real path: `hmmlearn.hmm.GaussianHMM` on [z-scored level, abs return].
Fallback: quantile + volatility rules on the same two features.

Interface:
    res = detect_regimes(dates, net_settlements)
    res.labels        -> list[str] per day
    res.current       -> str (last day's regime)
    res.state_stats   -> {label: {"mean_inr":..., "days":..., "share":...}}
    res.engine        -> "hmmlearn" | "fallback"
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .. import config as C

try:
    from hmmlearn.hmm import GaussianHMM  # type: ignore

    _HAVE_HMM = True
except Exception:  # noqa: BLE001
    _HAVE_HMM = False


@dataclass
class RegimeResult:
    labels: list[str]
    current: str
    state_stats: dict = field(default_factory=dict)
    engine: str = "fallback"
    transition_matrix: list[list[float]] | None = None


def _features(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    # 14-day rolling mean as trend; level feature = deviation from trend
    k = 14
    trend = np.convolve(x, np.ones(k) / k, mode="same")
    trend = np.where(trend <= 0, np.mean(x), trend)
    level = (x - trend) / trend
    ret = np.zeros_like(x)
    ret[1:] = np.diff(np.log(np.where(x <= 0, np.nan, x)))
    ret = np.nan_to_num(ret)
    absret = np.abs(ret)
    f = np.column_stack([_z(level), _z(absret)])
    return np.nan_to_num(f)


def _z(a: np.ndarray) -> np.ndarray:
    s = np.std(a)
    return (a - np.mean(a)) / (s if s > 1e-9 else 1.0)


def detect_regimes(dates, net_settlements) -> RegimeResult:
    x = np.asarray(net_settlements, dtype=float)
    if x.size < 60:
        lbl = ["low_season"] * x.size
        return RegimeResult(lbl, lbl[-1] if lbl else "low_season", {}, "fallback")

    feats = _features(x)

    if _HAVE_HMM:
        try:
            model = GaussianHMM(n_components=C.HMM_STATES, covariance_type="diag",
                                n_iter=200, random_state=C.RANDOM_SEED)
            model.fit(feats)
            states = model.predict(feats)
            label_map = _label_states(model.means_, x, states)
            labels = [label_map[s] for s in states]
            return RegimeResult(
                labels, labels[-1],
                _state_stats(labels, x),
                "hmmlearn",
                model.transmat_.round(3).tolist(),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[cfo.hmm] hmmlearn fit failed ({exc!r}) -> fallback")

    # ---- fallback: rule-based on level + vol ----
    level = feats[:, 0]
    vol = feats[:, 1]
    labels = []
    for lv, vv in zip(level, vol):
        if lv < -0.8 and vv > 0.8:
            labels.append("stress")
        elif lv > 0.4:
            labels.append("high_season")
        else:
            labels.append("low_season")
    return RegimeResult(labels, labels[-1], _state_stats(labels, x), "fallback")


def _label_states(means: np.ndarray, x: np.ndarray, states: np.ndarray) -> dict[int, str]:
    """Map raw HMM state ids -> semantic labels by their settlement level/vol."""
    stats = []
    for s in range(means.shape[0]):
        mask = states == s
        stats.append((s, x[mask].mean() if mask.any() else 0.0,
                      x[mask].std() if mask.any() else 0.0))
    # highest mean -> high_season ; lowest mean OR highest vol -> stress ; rest low
    by_mean = sorted(stats, key=lambda t: t[1])
    by_vol = sorted(stats, key=lambda t: t[2])
    out: dict[int, str] = {}
    out[by_mean[-1][0]] = "high_season"
    stress_id = by_vol[-1][0] if by_vol[-1][0] != by_mean[-1][0] else by_mean[0][0]
    out[stress_id] = "stress"
    for s, _, _ in stats:
        out.setdefault(s, "low_season")
    return out


def _state_stats(labels: list[str], x: np.ndarray) -> dict:
    out: dict[str, dict] = {}
    arr = np.asarray(labels)
    for lab in set(labels):
        mask = arr == lab
        out[lab] = {
            "mean_inr": round(float(x[mask].mean()), 2),
            "days": int(mask.sum()),
            "share": round(float(mask.mean()), 3),
        }
    return out
