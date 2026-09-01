// Types mirrored from the Cash Flow Oracle `/oracle/*` responses (Track 04).

export interface OracleMerchant {
  merchant_id: string;
  name: string;
  category: string;
  city_tier: number;
  current_cash_position: number;
  operating_threshold: number;
}

export interface CashCurvePoint {
  date: string;
  balance: number;
  lower: number;
  upper: number;
  is_forecast: boolean;
  regime: string;
}

export interface CashStressPeriod {
  start: string;
  end: string;
  days: number;
  trough_date: string;
  trough_balance: number;
  min_balance_lower: number;
  shortfall_at_trough: number;
}

export interface CarryCost {
  shortfall_inr: number;
  days_early: number;
  carry_cost_inr: number;
  late_payment_penalty_avoided_inr: number;
  net_benefit_inr: number;
  recommendation: "borrow_early" | "delay_or_downsize";
  explanation: string;
}

export interface PeerMetric {
  you: number;
  peer_avg: number | null;
  peer_min: number | null;
  peer_max: number | null;
  percentile: number;
  distribution: number[];
  plain: string;
}

export interface PeerComparison {
  peer_group: string;
  n_peers: number;
  category: string;
  city_tier: number;
  volatility: PeerMetric;
  avg_daily_settlement: PeerMetric;
  stress_frequency?: {
    you_per_year: number | null;
    peer_avg_per_year: number | null;
    plain: string;
  };
  merchant_id?: string;
  merchant_name?: string;
}

export interface OracleForecast {
  merchant_id: string;
  archetype: string;
  engine: string;
  generated_on: string;

  current_cash_position: number;
  cash_on_hand: number;
  trailing_7d_net_inr: number;
  forecast_total_inr: number;

  regime: string;
  regime_confidence: number;
  regime_description: string;
  regime_history: { date: string; regime: string }[];
  regime_stats: Record<string, { mean_inr: number; days: number; share: number }>;

  volatility: { historical_daily_pct: number; forecast_daily_pct: number; ratio: number };

  forecast_curve: { date: string; yhat: number; lower: number; upper: number }[];
  operating_threshold: number;
  cash_position_curve: CashCurvePoint[];
  cash_stress_periods: CashStressPeriod[];
  stress_periods: unknown[];

  peer_comparison: PeerComparison;
  anomaly_flag: boolean;
  anomaly_explanation: string | null;

  credit_apply_by_date: string | null;
  carry_cost_analysis: CarryCost;
  credit_recommendation: string;

  forecast_accuracy_mape: number | null;
  next_stress_days: number | null;
  current_cash_trend_pct: number;
  festival_markers: { name: string; date: string; days_out: number }[];
}

export interface LLMRecommendation {
  recommendation: string;
  source: "llm" | "template";
  model: string;
  cached: boolean;
  generated_on: string;
}

export interface AnomalyItem {
  date: string;
  direction: "above" | "below";
  kind: "SPIKE" | "DIP";
  magnitude_sigma: number;
  actual_inr: number;
  expected_inr: number;
  explanation: string;
}

export interface AnomalyFeed {
  merchant_id: string;
  merchant_name: string;
  lookback_days: number;
  sigma_threshold: number;
  count: number;
  anomalies: AnomalyItem[];
}

export interface Fingerprint {
  merchant_id: string;
  merchant_name: string;
  category: string;
  fingerprint: {
    weekday_labels: string[];
    week_count: number;
    matrix: (number | null)[][];
    raw_inr: (number | null)[][];
  };
  festival_response_curves: {
    weeks_offset: number[];
    curves: Record<string, (number | null)[]>;
  };
}

export type ShockType =
  | "discount_sale"
  | "marketing_spend"
  | "inventory_purchase"
  | "payment_gateway_outage";

export interface ScenarioResult {
  scenario_id: string;
  merchant_id: string;
  shock: {
    type: ShockType;
    magnitude_pct: number;
    start_date: string;
    duration_days: number;
  };
  original_forecast_curve: CashCurvePoint[];
  shocked_forecast_curve: CashCurvePoint[];
  forecast_dates: string[];
  operating_threshold: number;
  delta_cash_position_final_inr: number;
  delta_min_balance_inr: number;
  original_stress_periods: CashStressPeriod[];
  shocked_stress_periods: CashStressPeriod[];
  new_stress_periods: CashStressPeriod[];
  new_stress_count: number;
  stress_message: string;
  updated_credit_recommendation: {
    changed: boolean;
    summary: string;
    apply_by_date?: string | null;
    carry_cost_analysis?: CarryCost;
  };
}

export interface AlertPreview {
  merchant_id: string;
  title: string;
  body: string;
  urgency: "low" | "medium" | "high";
  recommended_action: string;
  apply_by_date: string | null;
  sender: string;
}
