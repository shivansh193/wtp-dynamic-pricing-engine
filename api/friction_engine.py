"""
Friction-Aware Conversion Engine — Step 1: the friction classifier.

Runs AFTER the WTP estimator and BEFORE the final pricing decision. For each
shopper it names the *specific barrier to purchase* (primary + secondary) so the
intervention library (Step 2) can target it, instead of attaching a generic perk.

Hybrid design:
  - a transparent rule scorer gives every friction type a 0..1 score from the
    customer signals (this is what a merchant can reason about), and
  - a LightGBM multiclass classifier, trained on rule-derived labels + injected
    noise (see model/train_friction.py), refines the call and gives calibrated
    probabilities + SHAP attributions.
The two are blended; if the model artifact is missing the engine degrades to
pure rules.

Friction types
--------------
price_sensitivity   low WTP, Tier 3, COD-leaning, high returns, thin AOV
trust_deficit       new account, VPN/DC network, low cross-merchant trust, few merchants
decision_paralysis  abandons carts, late-night session, repeat visits, WTP on the fence
payment_friction    COD-preferring but COD-ineligible, card-first shown to a UPI shopper,
                    weak payment-success history
delivery_anxiety    high returns, Tier 2/3, electronics / high-value, first buy in category
urgency_insensitive high WTP, repeat buyer, morning, Tier 1 — wants quality signals, not urgency
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

FRICTION_TYPES = [
    "price_sensitivity",
    "trust_deficit",
    "decision_paralysis",
    "payment_friction",
    "delivery_anxiety",
    "urgency_insensitive",
]

# rough category AOV centres (INR) - also used by the anchoring intervention
CATEGORY_AOV = {
    "fashion": 1900,
    "electronics": 8200,
    "grocery": 1100,
    "home": 2600,
    "beauty": 1300,
}
HIGH_VALUE_CATEGORIES = {"electronics", "home"}


@dataclass
class FrictionContext:
    """Signals about the shopper's journey that aren't in the base profile.
    The API fills these from the session store; all optional."""
    cart_abandonment_rate: float = 0.0       # 0..1
    repeat_sessions_on_product: int = 0      # how many times seen this product
    first_purchase_in_category: bool = False
    session_minutes: float = 0.0
    cod_eligible: bool | None = None         # provisional, from pricing thresholds


@dataclass
class FrictionResult:
    primary: str
    secondary: str
    confidence: float                         # 0..1 on the primary call
    scores: dict[str, float]                  # blended 0..1 per friction type
    rule_scores: dict[str, float]
    model_scores: dict[str, float] | None
    drivers: list[dict[str, Any]] = field(default_factory=list)   # top signals
    engine: str = "rules"                     # "rules" | "hybrid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "confidence": round(self.confidence, 4),
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "drivers": self.drivers,
            "engine": self.engine,
        }


# --------------------------------------------------------------------------- #
# Rule scorer
# --------------------------------------------------------------------------- #
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _wtp_norm(wtp: float) -> float:
    """0 at the -10% floor, 1 at the +15% cap."""
    return _clamp01((wtp - 0.90) / 0.25)


def rule_scores(signals: dict, wtp_multiplier: float,
                ctx: FrictionContext) -> dict[str, float]:
    tier = int(signals.get("city_tier", 2) or 2)
    pay = signals.get("payment_method_preference", "UPI")
    split = signals.get("payment_split") or {}
    cod_share = float(split.get("COD", 0.0) or 0.0)
    cc_share = float(split.get("Credit_Card", 0.0) or 0.0)
    upi_share = float(split.get("UPI", 0.0) or 0.0)
    rr = float(signals.get("return_rate", 0.15) or 0.15)
    trust = float(signals.get("cross_merchant_trust_score", 55) or 55)
    ipm = float(signals.get("ip_trust_multiplier", 0.9) or 0.9)
    ip_type = signals.get("ip_type", "unknown")
    acct_age = float(signals.get("account_age_days", 200) or 200)
    n_merch = int(signals.get("num_merchants_transacted", 5) or 5)
    aov = float(signals.get("historical_aov", 2000) or 2000)
    cat = signals.get("product_category", "fashion")
    cart = float(signals.get("cart_value", signals.get("list_price", 2000)) or 2000)
    tod = signals.get("time_of_day", "evening")
    psr = float(signals.get("payment_success_rate", 0.9) or 0.9)
    wn = _wtp_norm(wtp_multiplier)
    cat_aov = CATEGORY_AOV.get(cat, 2500)
    cod_elig = ctx.cod_eligible if ctx.cod_eligible is not None else (trust > 55)

    s = {t: 0.0 for t in FRICTION_TYPES}

    # ---- price_sensitivity ----
    s["price_sensitivity"] = _clamp01(
        0.38 * (1.0 - wn)
        + 0.18 * (tier == 3)
        + 0.10 * max(cod_share, 1.0 if pay == "COD" else 0.0)
        + 0.18 * _clamp01(rr / 0.4)
        + 0.16 * _clamp01((cat_aov - aov) / cat_aov + 0.2)
    )

    # ---- trust_deficit ----
    s["trust_deficit"] = _clamp01(
        0.24 * (acct_age < 90)
        + 0.12 * (acct_age < 30)
        + 0.22 * (ip_type in {"vpn", "tor", "datacenter"})
        + 0.22 * (1.0 - _clamp01(trust / 100.0))
        + 0.10 * (1.0 - _clamp01((ipm - 0.3) / 0.7))
        + 0.10 * (n_merch <= 2)
    )

    # ---- decision_paralysis ----
    on_fence = 1.0 - _clamp01(abs(wtp_multiplier - 1.0) / 0.12)
    s["decision_paralysis"] = _clamp01(
        0.30 * _clamp01(ctx.cart_abandonment_rate)
        + 0.18 * (tod in {"evening", "night"})
        + 0.24 * _clamp01(ctx.repeat_sessions_on_product / 3.0)
        + 0.28 * on_fence
    )

    # ---- payment_friction ----
    cod_pref_blocked = (pay == "COD" or cod_share > 0.4) and not cod_elig
    upi_shopper_card_first = (pay == "UPI" or upi_share > 0.4) and wn >= 0.6
    s["payment_friction"] = _clamp01(
        0.58 * cod_pref_blocked
        + 0.26 * upi_shopper_card_first
        + 0.30 * _clamp01((0.95 - psr) / 0.2)
    )

    # ---- delivery_anxiety ----
    s["delivery_anxiety"] = _clamp01(
        0.30 * _clamp01(rr / 0.4)
        + 0.16 * (tier in {2, 3})
        + 0.24 * (cat in HIGH_VALUE_CATEGORIES or cart >= 5000)
        + 0.30 * ctx.first_purchase_in_category
    )

    # ---- urgency_insensitive ----
    s["urgency_insensitive"] = _clamp01(
        0.34 * wn
        + 0.20 * _clamp01(n_merch / 20.0)
        + 0.16 * (tod == "morning")
        + 0.14 * (tier == 1)
        + 0.16 * _clamp01((trust - 60) / 40.0)
    )
    return s


def _softmax(d: dict[str, float], temp: float = 0.35) -> dict[str, float]:
    xs = {k: v / temp for k, v in d.items()}
    m = max(xs.values())
    ex = {k: math.exp(v - m) for k, v in xs.items()}
    z = sum(ex.values()) or 1.0
    return {k: v / z for k, v in ex.items()}


def _drivers_from_rules(signals: dict, ctx: FrictionContext, primary: str) -> list[dict]:
    """Plain-English top signals behind the primary friction call."""
    tier = int(signals.get("city_tier", 2) or 2)
    d: list[tuple[str, float]] = []
    rr = float(signals.get("return_rate", 0.15) or 0.15)
    trust = float(signals.get("cross_merchant_trust_score", 55) or 55)
    acct = float(signals.get("account_age_days", 200) or 200)
    if primary == "price_sensitivity":
        d = [("low willingness-to-pay signal", 0.4),
             (f"Tier {tier} location", 0.2 if tier == 3 else 0.05),
             (f"{rr*100:.0f}% return rate", min(rr / 0.4, 1) * 0.25)]
    elif primary == "trust_deficit":
        d = [(f"account age {acct/30:.0f} months", 0.3 if acct < 90 else 0.1),
             (f"cross-merchant trust {trust:.0f}/100", (1 - trust / 100) * 0.4),
             (f"network: {signals.get('ip_type','unknown')}",
              0.3 if signals.get("ip_type") in {"vpn", "tor", "datacenter"} else 0.05)]
    elif primary == "decision_paralysis":
        d = [("session in the evening/night", 0.25),
             (f"{ctx.repeat_sessions_on_product} prior visits to this product",
              min(ctx.repeat_sessions_on_product / 3, 1) * 0.3),
             ("WTP sits right at list price (on the fence)", 0.35)]
    elif primary == "payment_friction":
        d = [("prefers COD but COD isn't available here", 0.45),
             (f"payment-success rate {signals.get('payment_success_rate',0.9)}", 0.3)]
    elif primary == "delivery_anxiety":
        d = [(f"{rr*100:.0f}% return rate", min(rr / 0.4, 1) * 0.35),
             (f"{signals.get('product_category','')} category", 0.25),
             ("first purchase in this category", 0.3 if ctx.first_purchase_in_category else 0.05)]
    elif primary == "urgency_insensitive":
        d = [("high willingness-to-pay", 0.35),
             (f"shopped {signals.get('num_merchants_transacted',5)} merchants (repeat buyer)", 0.25),
             (f"trust {trust:.0f}/100", (trust - 60) / 40 * 0.2 if trust > 60 else 0.02)]
    return [{"signal": s, "weight": round(w, 3)} for s, w in
            sorted(d, key=lambda t: -t[1]) if w > 0][:3]


# --------------------------------------------------------------------------- #
# Hybrid classifier
# --------------------------------------------------------------------------- #
class FrictionModel:
    """Loads the trained LightGBM refiner if present; otherwise pure rules."""

    def __init__(self) -> None:
        self._bundle = None
        self._load()

    def _load(self) -> None:
        try:
            from pathlib import Path

            import joblib

            p = Path(__file__).resolve().parents[1] / "model" / "artifacts" / "friction_classifier.joblib"
            if p.exists():
                self._bundle = joblib.load(p)
                print(f"[friction] model loaded ({p.name})")
        except Exception as exc:  # noqa: BLE001
            print(f"[friction] model load skipped: {exc!r}")

    @property
    def has_model(self) -> bool:
        return self._bundle is not None

    def _model_scores(self, signals: dict, wtp_multiplier: float) -> dict[str, float] | None:
        if not self._bundle:
            return None
        try:
            import numpy as np

            b = self._bundle
            cat_maps = b["category_maps"]
            cats = set(b.get("categorical_features", []))
            order = b["model"].feature_name()
            derived = {
                "wtp_multiplier": float(wtp_multiplier),
                "wtp_norm": _wtp_norm(wtp_multiplier),
                "is_new_account": 1.0 if float(signals.get("account_age_days", 200) or 200) < 90 else 0.0,
            }
            row = []
            for f in order:
                if f in derived:
                    row.append(derived[f])
                elif f in cats:
                    row.append(float(cat_maps.get(f, {}).get(str(signals.get(f)), -1)))
                else:
                    v = signals.get(f)
                    try:
                        row.append(float(v))
                    except (TypeError, ValueError):
                        row.append(float("nan"))
            proba = b["model"].predict(np.array([row], dtype="float64"),
                                       num_iteration=b["model"].best_iteration)[0]
            return {c: float(p) for c, p in zip(b["classes"], proba)}
        except Exception as exc:  # noqa: BLE001
            print(f"[friction] model inference failed: {exc!r}")
            return None


_model: FrictionModel | None = None


def get_model() -> FrictionModel:
    global _model
    if _model is None:
        _model = FrictionModel()
    return _model


def classify_friction(
    signals: dict,
    *,
    wtp_multiplier: float,
    context: FrictionContext | None = None,
) -> FrictionResult:
    ctx = context or FrictionContext()
    rs = rule_scores(signals, wtp_multiplier, ctx)
    rule_soft = _softmax(rs)

    ms = get_model()._model_scores(signals, wtp_multiplier)
    if ms:
        blended = {t: 0.5 * rule_soft.get(t, 0.0) + 0.5 * ms.get(t, 0.0) for t in FRICTION_TYPES}
        engine = "hybrid"
    else:
        blended = rule_soft
        engine = "rules"

    ranked = sorted(FRICTION_TYPES, key=lambda t: -blended[t])
    primary, secondary = ranked[0], ranked[1]
    top = blended[primary]
    gap = top - blended[secondary]
    confidence = _clamp01(0.45 + 0.9 * gap + 0.25 * (top - 1.0 / len(FRICTION_TYPES)))

    return FrictionResult(
        primary=primary,
        secondary=secondary,
        confidence=confidence,
        scores=blended,
        rule_scores=rs,
        model_scores=ms,
        drivers=_drivers_from_rules(signals, ctx, primary),
        engine=engine,
    )
