"""
GARCH(1,1) volatility model on daily settlement amounts.

Real path: `arch.arch_model` on the percentage change of net settlements.
Fallback: exponentially-weighted rolling standard deviation of returns.

Both expose the same interface:
    res = fit_garch(net_settlements: np.ndarray)
    res.conditional_vol   -> np.ndarray, same length (annualised-ish, in return units)
    res.forecast_vol(h)   -> np.ndarray of length h
    res.engine            -> "arch" | "fallback"
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import config as C

try:
    from arch import arch_model  # type: ignore

    _HAVE_ARCH = True
except Exception:  # noqa: BLE001
    _HAVE_ARCH = False


@dataclass
class GarchResult:
    conditional_vol: np.ndarray
    _omega: float
    _alpha: float
    _beta: float
    _last_var: float
    _last_resid2: float
    engine: str

    def forecast_vol(self, horizon: int) -> np.ndarray:
        """Iterate the GARCH(1,1) variance recursion forward."""
        out = np.empty(horizon)
        var = self._last_var
        resid2 = self._last_resid2
        uncond = self._omega / max(1e-12, 1 - self._alpha - self._beta)
        for h in range(horizon):
            var = self._omega + self._alpha * resid2 + self._beta * var
            # beyond 1 step ahead E[resid^2] = var
            resid2 = var
            # pull gently toward the unconditional level for long horizons
            var = 0.9 * var + 0.1 * uncond
            out[h] = np.sqrt(max(var, 1e-12))
        return out


def _returns(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = np.where(x <= 0, np.nan, x)
    r = np.diff(np.log(x))
    return r[np.isfinite(r)]


def fit_garch(net_settlements: np.ndarray) -> GarchResult:
    r = _returns(net_settlements) * 100.0  # arch likes percent returns
    if r.size < 30:
        # not enough data - flat vol
        v = np.full(max(r.size, 1), np.std(r) if r.size else 0.01)
        return GarchResult(v, 0.0, 0.0, 0.0, float(v[-1] ** 2), float(v[-1] ** 2), "fallback")

    if _HAVE_ARCH:
        try:
            am = arch_model(r, p=C.GARCH_P, q=C.GARCH_Q, mean="constant", vol="GARCH",
                            dist="t")
            fit = am.fit(disp="off")
            cond = np.asarray(fit.conditional_volatility) / 100.0
            p = fit.params
            omega = float(p.get("omega", 0.0))
            alpha = float(p.get("alpha[1]", 0.0))
            beta = float(p.get("beta[1]", 0.0))
            last_var = float(fit.conditional_volatility[-1] ** 2)
            last_resid2 = float((r[-1] - float(p.get("mu", 0.0))) ** 2)
            return GarchResult(cond, omega / 1e4, alpha, beta,
                               last_var / 1e4, last_resid2 / 1e4, "arch")
        except Exception as exc:  # noqa: BLE001
            print(f"[cfo.garch] arch fit failed ({exc!r}) -> fallback")

    # ---- fallback: EWMA vol of returns ----
    lam = 0.94
    var = np.empty(r.size)
    var[0] = np.var(r[:20]) if r.size >= 20 else np.var(r)
    for t in range(1, r.size):
        var[t] = lam * var[t - 1] + (1 - lam) * r[t - 1] ** 2
    cond = np.sqrt(var) / 100.0
    return GarchResult(cond, float(np.mean(var) * 0.02) / 1e4, 0.06, 0.90,
                       float(var[-1]) / 1e4, float(r[-1] ** 2) / 1e4, "fallback")
