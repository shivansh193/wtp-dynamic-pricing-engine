import type { CustomerSignals, Preset } from "./types";

// The demo product. Brief: Nike Air Max, ₹4,999 list price.
export const PRODUCT = {
  name: "Nike Air Max (2026)",
  brand: "Nike",
  list_price: 4999,
  category: "fashion" as const,
  emoji: "\u{1F45F}",
  seller: "RunHub Official Store",
};

export const PRESET_LABELS: Record<Preset, { label: string; blurb: string }> = {
  random: {
    label: "Random",
    blurb: "System picks a realistic random profile",
  },
  high: {
    label: "High Income",
    blurb: "Tier 1 · iPhone · Credit Card · 40+ prepaid orders · <5% returns",
  },
  mid: {
    label: "Mid Income",
    blurb: "Tier 2 · Android Premium · UPI · 15–25 prepaid orders · 10–15% returns",
  },
  low: {
    label: "Low Income",
    blurb: "Tier 3 · Android Budget · COD · <5 prepaid orders · >25% returns",
  },
  custom: {
    label: "Custom",
    blurb: "Set every field manually",
  },
};

export const DEVICE_LABEL: Record<string, string> = {
  Android_budget: "Budget Android",
  Android_premium: "Premium Android",
  iPhone: "iPhone",
  Desktop: "Desktop",
};

export const PAYMENT_LABEL: Record<string, string> = {
  UPI: "UPI",
  Credit_Card: "Credit Card",
  Debit_Card: "Debit Card",
  COD: "Cash on Delivery",
  Wallet: "Wallet",
};

export const OFFER_LABEL: Record<string, string> = {
  extended_warranty: "Free 1-year extended warranty",
  priority_support: "Priority customer support",
  free_delivery: "Free delivery",
  cashback_5pct: "5% cashback",
  none: "No additional offer",
};

export const STATUS_STYLE: Record<
  string,
  { label: string; cls: string }
> = {
  pending: { label: "pending", cls: "bg-slate-100 text-slate-600" },
  priced: { label: "priced", cls: "bg-blue-100 text-blue-700" },
  converted: { label: "converted", cls: "bg-emerald-100 text-emerald-700" },
  abandoned: { label: "abandoned", cls: "bg-amber-100 text-amber-700" },
};

export function inr(n: number | null | undefined): string {
  if (n == null) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

/** Build a /personalize payload from a (possibly edited) session config. */
export function signalsFromConfig(
  cfg: Record<string, any>,
  sessionId?: string,
): Partial<CustomerSignals> & { list_price: number } {
  return {
    session_id: sessionId,
    ip: cfg.ip,
    ip_type: cfg.vpn ? "vpn" : cfg.ip_type ?? null,
    list_price: cfg.list_price ?? PRODUCT.list_price,
    product_category: "fashion",
    pin_code: cfg.pin_code,
    city_tier: cfg.city_tier,
    income_tier: cfg.income_tier,
    device_type: cfg.device_type,
    payment_method_preference: cfg.payment_method_preference,
    referral_source: cfg.referral_source ?? "organic",
    return_rate: cfg.return_rate,
    payment_success_rate: cfg.payment_success_rate,
    cod_completion_rate: cfg.cod_completion_rate,
    cross_merchant_trust_score: cfg.cross_merchant_trust_score,
    num_merchants_transacted: cfg.num_merchants_transacted,
    account_age_days: cfg.account_age_days,
  };
}
