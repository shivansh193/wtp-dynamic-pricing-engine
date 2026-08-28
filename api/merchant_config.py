"""
Merchant-tunable pricing rules.

A real merchant should be able to dial the engine to their risk appetite:
turn the whole markup off, cap how far it can go either way, switch individual
perks on/off, and retune how the cross-merchant trust score is built. This is a
single-merchant in-memory config for the demo (one row); a production build
keys it by merchant_id.

Everything has a sensible default so an untouched merchant gets the same
behaviour as before this module existed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any


@dataclass
class OfferToggles:
    """Which checkout perks the merchant allows the engine to attach."""
    extended_warranty: bool = True
    priority_support: bool = True
    free_delivery: bool = True
    cashback_5pct: bool = True
    instant_refund: bool = True          # the "instant refund" eligibility badge

    def allowed(self, offer: str) -> bool:
        return bool(getattr(self, offer, True))


@dataclass
class TrustWeights:
    """Coefficients for the cross-merchant trust score (0-100).

    trust = base
          + w_prepaid_order      * prepaid_orders
          - w_return_rate * 100  * return_rate
          + w_credit_card_share  * (credit-card share of payments)
          - w_cod_share          * (COD share of payments)
          + tier1_adj | tier3_adj
          - w_vpn_penalty        (if on VPN / public network)
    """
    base: float = 44.0
    w_prepaid_order: float = 1.10
    w_return_rate: float = 0.50
    w_credit_card_share: float = 14.0
    w_cod_share: float = 16.0
    w_vpn_penalty: float = 26.0
    tier1_adj: float = 6.0
    tier3_adj: float = -4.0


@dataclass
class MerchantConfig:
    # ---- the master lever ----
    markup_enabled: bool = True           # off => price is never above list
    max_markup_pct: float = 0.15          # 0.00 .. 0.15
    max_discount_pct: float = 0.10        # 0.00 .. 0.10  (positive number)

    # ---- eligibility thresholds ----
    cod_trust_min: float = 60.0
    cod_completion_min: float = 0.80
    cod_pref_trust_min: float = 25.0      # a COD-native shopper needs less trust
    cod_pref_completion_min: float = 0.75
    instant_refund_trust_min: float = 80.0

    # ---- what changes with real Razorpay data ----
    gross_margin: float = 0.45            # for the "expected margin vs flat" sim

    offers: OfferToggles = field(default_factory=OfferToggles)
    trust_weights: TrustWeights = field(default_factory=TrustWeights)

    # ------------------------------------------------------------------ #
    def effective_caps(self) -> tuple[float, float]:
        """(cap_up, cap_down) as signed fractions of list price."""
        up = self.max_markup_pct if self.markup_enabled else 0.0
        return round(float(up), 4), round(-abs(float(self.max_discount_pct)), 4)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def merged(self, patch: dict[str, Any]) -> "MerchantConfig":
        """Return a copy with `patch` applied (shallow, plus nested offers /
        trust_weights)."""
        patch = dict(patch or {})
        offers = patch.pop("offers", None)
        weights = patch.pop("trust_weights", None)
        allowed = {f for f in self.__dataclass_fields__ if f not in
                   ("offers", "trust_weights")}
        clean = {k: v for k, v in patch.items() if k in allowed}
        new = replace(self, **clean)
        if isinstance(offers, dict):
            new.offers = replace(new.offers,
                                 **{k: bool(v) for k, v in offers.items()
                                    if k in OfferToggles.__dataclass_fields__})
        if isinstance(weights, dict):
            new.trust_weights = replace(
                new.trust_weights,
                **{k: float(v) for k, v in weights.items()
                   if k in TrustWeights.__dataclass_fields__})
        # clamp to sane bounds
        new.max_markup_pct = float(min(max(new.max_markup_pct, 0.0), 0.15))
        new.max_discount_pct = float(min(max(new.max_discount_pct, 0.0), 0.10))
        new.gross_margin = float(min(max(new.gross_margin, 0.05), 0.9))
        return new


# process-wide singleton (single-merchant demo)
_config = MerchantConfig()


def get_config() -> MerchantConfig:
    return _config


def update_config(patch: dict[str, Any]) -> MerchantConfig:
    global _config
    _config = _config.merged(patch)
    return _config


def reset_config() -> MerchantConfig:
    global _config
    _config = MerchantConfig()
    return _config
