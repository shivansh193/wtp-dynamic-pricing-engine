// Shapes mirrored from the FastAPI `/personalize` + `/metrics` responses.

export interface CustomerSignals {
  session_id?: string;
  ip?: string;
  list_price: number;
  product_category: "fashion" | "electronics" | "grocery" | "home" | "beauty";
  device_type: "Android_budget" | "Android_premium" | "iPhone" | "Desktop";
  city_tier: 1 | 2 | 3;
  pin_code?: string;
  income_tier?: "low" | "lower_mid" | "mid" | "upper_mid" | "high";
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

// ---- link-generator demo flow ----

export type Preset = "random" | "high" | "mid" | "low" | "custom";

export interface CustomSessionFields {
  pin_code?: string;
  device_type?: CustomerSignals["device_type"];
  payment_method_preference?: CustomerSignals["payment_method_preference"];
  prepaid_orders?: number;
  return_rate?: number;
  vpn?: boolean;
  city_tier?: 1 | 2 | 3;
}

export interface SessionConfig {
  list_price: number;
  product_category: string;
  pin_code: string;
  city: string;
  city_tier: 1 | 2 | 3;
  income_tier: string;
  device_type: CustomerSignals["device_type"];
  payment_method_preference: CustomerSignals["payment_method_preference"];
  referral_source: string;
  prepaid_orders: number;
  vpn: boolean;
  return_rate: number;
  payment_success_rate: number;
  cod_completion_rate: number;
  cross_merchant_trust_score: number;
  num_merchants_transacted: number;
  account_age_days: number;
  ip_type: string | null;
  ip: string;
  preset: string;
}

export interface SessionCreateResponse {
  session_id: string;
  merchant_id: string;
  preset: string;
  config: SessionConfig;
  segment_key: string;
  customer_url: string;
  merchant_url: string;
  qr_code_base64: string;
  status: string;
  created_at: string;
}

export type SessionStatus = "pending" | "priced" | "converted" | "abandoned";

export interface SessionInfo {
  session_id: string;
  merchant_id: string;
  preset: string;
  config: SessionConfig;
  status: SessionStatus;
  created_at?: string;
  priced_at?: string;
  completed_at?: string;
  list_price?: number;
  price_shown?: number;
  wtp_score?: number;
  offer_type?: string;
  segment_key?: string;
  result?: PricingResponse;
}

export interface SegmentStats {
  segment_key: string;
  n_observations: number;
  n_customers_like_this: number;
  prior: { mean: number; sd: number };
  observed: { mean_wtp: number | null; sd_wtp: number | null };
  posterior: { mean_wtp: number; sd: number; ci_95: [number, number] };
  conversion_curve: { price_multiplier: number; conversion_probability: number }[];
  revenue_simulation: {
    expected_revenue_wtp_pricing: number;
    expected_revenue_flat_pricing: number;
    absolute_lift: number;
    pct_lift: number;
  };
}

export interface WsMessage {
  type:
    | "hello"
    | "session.created"
    | "session.priced"
    | "session.completed"
    | "session.abandoned";
  session: SessionInfo | null;
  ts?: string;
  backend?: string;
}
