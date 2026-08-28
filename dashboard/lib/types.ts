// Shapes mirrored from the FastAPI `/personalize` + `/metrics` responses.

export interface CustomerSignals {
  session_id?: string;
  ip?: string;
  list_price: number;
  product_category: "fashion" | "electronics" | "grocery" | "home" | "beauty";
  device_type: "Android_budget" | "Android_premium" | "iPhone" | "Desktop";
  city_tier: 1 | 2 | 3;
  payment_method_preference: "UPI" | "Credit_Card" | "Debit_Card" | "COD" | "Wallet";
  referral_source: "organic" | "paid_ad" | "social" | "email" | "influencer";
  cross_merchant_trust_score: number;
  return_rate: number;
  payment_success_rate: number;
  cod_completion_rate: number;
  num_merchants_transacted: number;
  account_age_days: number;
  historical_aov?: number;
  ip_type?: string | null;
  ip_trust_multiplier?: number | null;
}

export interface ShapFeature {
  feature: string;
  value: string | number;
  shap: number;
}

export interface IpEnrichmentBrief {
  ip_type: string;
  ip_trust_multiplier: number;
  location_confidence: number;
  is_whitelisted: boolean;
  blocklist_hits: string[];
  geo_source: string;
  cache_hit: boolean;
  lookup_ms: number;
}

export interface PricingResponse {
  session_id: string;
  list_price: number;
  final_price: number;
  price_delta_pct: number;
  effective_multiplier: number;
  wtp_multiplier: number;
  conversion_probability: number | null;
  offer_type: string;
  offer_rationale: string;
  payment_methods_shown: string[];
  cod_eligible: boolean;
  instant_refund_eligible: boolean;
  reasoning: string;
  confidence: "high" | "medium" | "low";
  shap_top: ShapFeature[];
  ip_enrichment: IpEnrichmentBrief;
  latency_ms: number;
  budget_ms: number;
  budget_exceeded: boolean;
  timing_breakdown: Record<string, number>;
}

export interface MetricsResponse {
  decisions_logged: number;
  avg_wtp_by_segment?: {
    by_city_tier: Record<string, number>;
    by_device: Record<string, number>;
    by_payment_pref: Record<string, number>;
    top_10: { segment: string; avg_wtp: number }[];
  };
  conversion_rate_by_offer_type?: Record<string, number>;
  revenue_lift_simulation?: {
    expected_revenue_wtp_pricing: number;
    expected_revenue_flat_pricing: number;
    absolute_lift: number;
    pct_lift: number;
  };
  top_features_driving_wtp?: { feature: string; mean_abs_shap: number }[];
  traffic_quality?: {
    ip_type_counts: Record<string, number>;
    vpn_datacenter_tor_share_pct: number;
  };
  db_backend?: string;
  model?: Record<string, unknown>;
  note?: string;
}
