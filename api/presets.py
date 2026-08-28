"""
Customer-profile presets for the link-generator demo flow.

A "session config" is a superset of the model's CustomerSignals plus two
demo-facing knobs the checkout form exposes directly:
  * prepaid_orders  (0-50)  - how many past prepaid orders the shopper has
  * vpn             (bool)   - is the shopper on a VPN / public network

From those + the categorical picks we derive the behavioural signals the WTP
model actually consumes (trust score, payment-success rate, COD completion,
account age, num_merchants_transacted).
"""

from __future__ import annotations

import random
from typing import Any

# ---- PIN-code prefix -> city tier (major cities; first 3 digits) ----------- #
_PIN_TIER = {
    # Tier 1
    "400": 1, "110": 1, "560": 1, "500": 1, "600": 1, "700": 1, "411": 1,
    "380": 1, "122": 1, "201": 1,
    # Tier 2
    "302": 2, "226": 2, "440": 2, "452": 2, "462": 2, "641": 2, "682": 2,
    "160": 2, "530": 2, "395": 2, "390": 2, "422": 2,
    # Tier 3
    "800": 3, "834": 3, "781": 3, "492": 3, "342": 3, "221": 3, "625": 3,
    "431": 3, "248": 3, "734": 3, "273": 3, "284": 3, "590": 3, "517": 3,
}
_TIER_SAMPLE_PIN = {1: "400001", 2: "302001", 3: "800001"}
_TIER_CITY = {1: "Mumbai", 2: "Jaipur", 3: "Patna"}

# PIN prefix -> city name (for the "detected: <city> · Tier N" hint)
_PIN_CITY = {
    "400": "Mumbai", "110": "Delhi", "560": "Bengaluru", "500": "Hyderabad",
    "600": "Chennai", "700": "Kolkata", "411": "Pune", "380": "Ahmedabad",
    "122": "Gurugram", "201": "Noida",
    "302": "Jaipur", "226": "Lucknow", "440": "Nagpur", "452": "Indore",
    "462": "Bhopal", "641": "Coimbatore", "682": "Kochi", "160": "Chandigarh",
    "530": "Visakhapatnam", "395": "Surat", "390": "Vadodara", "422": "Nashik",
    "800": "Patna", "834": "Ranchi", "781": "Guwahati", "492": "Raipur",
    "342": "Jodhpur", "221": "Varanasi", "625": "Madurai", "431": "Aurangabad",
    "248": "Dehradun", "734": "Siliguri", "273": "Gorakhpur", "284": "Jhansi",
    "590": "Belagavi", "517": "Tirupati",
}


def city_name_from_pincode(pin: str | None) -> str:
    if pin and len(str(pin)) >= 3 and str(pin)[:3] in _PIN_CITY:
        return _PIN_CITY[str(pin)[:3]]
    return _TIER_CITY.get(city_tier_from_pincode(pin), "—")


def city_tier_from_pincode(pin: str | None) -> int:
    """Best-effort PIN -> tier. Falls back to the postal-zone first digit."""
    if not pin:
        return 2
    pin = str(pin).strip()
    if len(pin) >= 3 and pin[:3] in _PIN_TIER:
        return _PIN_TIER[pin[:3]]
    if pin[:1].isdigit():
        # zones 1/4/5/6/7 skew metro, 8 skews east/rural, else tier 2/3
        return {"1": 1, "4": 1, "5": 1, "6": 2, "7": 2, "8": 3}.get(pin[0], 2)
    return 2


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


DEFAULT_SPLITS = {
    1: {"UPI": 0.40, "Credit_Card": 0.34, "Debit_Card": 0.12, "COD": 0.04, "Wallet": 0.10},
    2: {"UPI": 0.52, "Credit_Card": 0.14, "Debit_Card": 0.16, "COD": 0.12, "Wallet": 0.06},
    3: {"UPI": 0.46, "Credit_Card": 0.04, "Debit_Card": 0.14, "COD": 0.30, "Wallet": 0.06},
}


def normalise_split(split: dict[str, float] | None, city_tier: int) -> dict[str, float]:
    """Clean a payment-method-share dict: keep known methods, drop negatives,
    renormalise to sum 1. Falls back to a tier-typical mix."""
    if not split:
        return dict(DEFAULT_SPLITS[city_tier])
    clean = {m: max(0.0, float(split.get(m, 0.0))) for m in PAYMENTS}
    total = sum(clean.values())
    if total <= 1e-6:
        return dict(DEFAULT_SPLITS[city_tier])
    return {m: round(v / total, 4) for m, v in clean.items()}


def derive_signals(
    *,
    city_tier: int,
    device_type: str,
    payment_method_preference: str | None = None,
    payment_split: dict[str, float] | None = None,
    prepaid_orders: int,
    return_rate: float,
    vpn: bool,
    pin_code: str | None,
    weights: "TrustWeights | None" = None,
) -> dict[str, Any]:
    """Turn the demo-form knobs into a full CustomerSignals-compatible dict.

    `payment_split` (method -> share, need not sum to 1) is the richer input:
    the *mix* of how a shopper pays feeds the trust score and COD reliability,
    not just their single favourite method. `payment_method_preference` is
    derived as the argmax and is what the pricing engine uses to order the
    checkout's payment buttons.
    """
    from .merchant_config import TrustWeights, get_config

    w = weights or (get_config().trust_weights if weights is None else TrustWeights())
    prepaid_orders = int(_clamp(prepaid_orders, 0, 50))
    return_rate = float(_clamp(return_rate, 0.0, 0.5))

    split = normalise_split(payment_split, city_tier)
    if not payment_method_preference:
        payment_method_preference = max(split, key=split.get)
    cc_share = split.get("Credit_Card", 0.0)
    cod_share = split.get("COD", 0.0)

    # behavioural derivations
    num_merchants = int(_clamp(round(prepaid_orders * 0.55) + 1, 1, 50))
    payment_success = _clamp(
        0.80 + prepaid_orders * 0.0040 + cc_share * 0.05 - cod_share * 0.03,
        0.75, 0.995,
    )
    # COD completion tracks the shopper's own delivery-acceptance habit - a
    # shopper who pays COD a lot AND keeps ordering is a reliable COD customer.
    cod_completion = _clamp(
        {1: 0.94, 2: 0.88, 3: 0.82}[city_tier]
        + prepaid_orders * 0.0025
        - return_rate * 0.15
        + cod_share * 0.10,
        0.45, 0.995,
    )
    account_age_days = int(_clamp(60 + prepaid_orders * 34, 30, 1800))

    trust = (
        w.base
        + prepaid_orders * w.w_prepaid_order
        - return_rate * 100 * w.w_return_rate
        + cc_share * w.w_credit_card_share
        - cod_share * w.w_cod_share
        + {1: w.tier1_adj, 2: 0.0, 3: w.tier3_adj}[city_tier]
        - (w.w_vpn_penalty if vpn else 0.0)
    )
    trust = _clamp(trust, 1, 99)

    income_tier = {1: "upper_mid", 2: "mid", 3: "lower_mid"}[city_tier]
    if trust >= 80 and city_tier == 1:
        income_tier = "high"
    elif trust <= 30 and city_tier == 3:
        income_tier = "low"

    return {
        "list_price": 4999,
        "product_category": "fashion",
        "pin_code": pin_code or _TIER_SAMPLE_PIN[city_tier],
        "city_tier": city_tier,
        "income_tier": income_tier,
        "device_type": device_type,
        "payment_method_preference": payment_method_preference,
        "payment_split": split,
        "referral_source": "organic",
        "prepaid_orders": prepaid_orders,
        "vpn": bool(vpn),
        "return_rate": round(return_rate, 4),
        "payment_success_rate": round(payment_success, 4),
        "cod_completion_rate": round(cod_completion, 4),
        "cross_merchant_trust_score": round(trust, 1),
        "num_merchants_transacted": num_merchants,
        "account_age_days": account_age_days,
        "ip_type": "vpn" if vpn else None,
        "ip": "146.70.0.5" if vpn else "49.36.128.5",
    }


# --------------------------------------------------------------------------- #
# The four fixed presets
# --------------------------------------------------------------------------- #
_FIXED = {
    "high": dict(city_tier=1, device_type="iPhone", prepaid_orders=44, return_rate=0.04,
                 vpn=False, pin_code="400001",
                 payment_split={"UPI": 0.25, "Credit_Card": 0.60, "Debit_Card": 0.05,
                                "COD": 0.02, "Wallet": 0.08}),
    "mid": dict(city_tier=2, device_type="Android_premium", prepaid_orders=20, return_rate=0.12,
                vpn=False, pin_code="302001",
                payment_split={"UPI": 0.55, "Credit_Card": 0.18, "Debit_Card": 0.15,
                               "COD": 0.08, "Wallet": 0.04}),
    "low": dict(city_tier=3, device_type="Android_budget", prepaid_orders=3, return_rate=0.30,
                vpn=False, pin_code="800001",
                payment_split={"UPI": 0.34, "Credit_Card": 0.02, "Debit_Card": 0.10,
                               "COD": 0.50, "Wallet": 0.04}),
}

DEVICES = ["Android_budget", "Android_premium", "iPhone", "Desktop"]
PAYMENTS = ["UPI", "Credit_Card", "Debit_Card", "COD", "Wallet"]
PRESETS = ["random", "high", "mid", "low", "custom"]


def _random_config(rng: random.Random) -> dict[str, Any]:
    tier = rng.choices([1, 2, 3], weights=[0.3, 0.35, 0.35])[0]
    device = rng.choices(
        DEVICES,
        weights={1: [0.15, 0.30, 0.35, 0.20], 2: [0.40, 0.35, 0.10, 0.15],
                 3: [0.62, 0.22, 0.04, 0.12]}[tier],
    )[0]
    # a randomised payment mix around the tier-typical split
    base = DEFAULT_SPLITS[tier]
    split = {m: max(0.0, rng.gauss(base[m], 0.08)) for m in PAYMENTS}
    s = sum(split.values()) or 1.0
    split = {m: round(v / s, 3) for m, v in split.items()}
    prepaid = int(rng.triangular(0, 50, {1: 32, 2: 16, 3: 5}[tier]))
    ret = round(_clamp(rng.gauss({1: 0.06, 2: 0.13, 3: 0.28}[tier], 0.05), 0.0, 0.5), 3)
    vpn = rng.random() < 0.08
    pin = _TIER_SAMPLE_PIN[tier][:3] + f"{rng.randint(1, 99):03d}"
    return dict(city_tier=tier, device_type=device, payment_split=split,
                prepaid_orders=prepaid, return_rate=ret, vpn=vpn, pin_code=pin)


def build_config(preset: str, custom: dict[str, Any] | None = None,
                 seed: int | None = None) -> dict[str, Any]:
    """Return a full session config for the given preset.

    `custom` (used when preset == 'custom', or to override any preset field):
      pin_code, device_type, payment_method_preference, prepaid_orders,
      return_rate, vpn
    """
    rng = random.Random(seed)
    preset = (preset or "random").lower()
    if preset not in PRESETS:
        preset = "random"

    if preset == "random":
        base = _random_config(rng)
    elif preset in _FIXED:
        base = dict(_FIXED[preset])
    else:  # custom
        base = dict(_FIXED["mid"])  # sensible starting point

    custom = custom or {}
    # pincode drives tier unless the caller pinned city_tier explicitly
    if custom.get("pin_code"):
        base["pin_code"] = str(custom["pin_code"])
        base["city_tier"] = city_tier_from_pincode(base["pin_code"])
    if custom.get("device_type"):
        base["device_type"] = custom["device_type"]
    if custom.get("payment_split"):
        base["payment_split"] = custom["payment_split"]
        base.pop("payment_method_preference", None)
    elif custom.get("payment_method_preference"):
        # single method chosen -> treat as a 100% split of that method
        base["payment_split"] = {custom["payment_method_preference"]: 1.0}
        base.pop("payment_method_preference", None)
    if custom.get("prepaid_orders") is not None:
        base["prepaid_orders"] = int(custom["prepaid_orders"])
    if custom.get("return_rate") is not None:
        base["return_rate"] = float(custom["return_rate"])
    if custom.get("vpn") is not None:
        base["vpn"] = bool(custom["vpn"])
    if custom.get("city_tier"):
        base["city_tier"] = int(custom["city_tier"])

    cfg = derive_signals(
        city_tier=base["city_tier"],
        device_type=base["device_type"],
        payment_method_preference=base.get("payment_method_preference"),
        payment_split=base.get("payment_split"),
        prepaid_orders=base["prepaid_orders"],
        return_rate=base["return_rate"],
        vpn=base["vpn"],
        pin_code=base.get("pin_code"),
    )
    cfg["preset"] = preset
    cfg["city"] = city_name_from_pincode(cfg.get("pin_code"))
    return cfg


def segment_key_for(cfg: dict[str, Any]) -> str:
    return "|".join(str(cfg.get(k, "?")) for k in
                    ("city_tier", "device_type", "payment_method_preference"))
