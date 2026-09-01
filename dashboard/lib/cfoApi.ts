import { API_BASE } from "./api";
import type {
  AlertPreview,
  AnomalyFeed,
  Fingerprint,
  LLMRecommendation,
  OracleForecast,
  OracleMerchant,
  PeerComparison,
  ScenarioResult,
  ShockType,
} from "./cfoTypes";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = b.detail ?? JSON.stringify(b);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return (await res.json()) as T;
}

export function getOracleMerchants() {
  return j<{ count: number; merchants: OracleMerchant[] }>("/oracle/merchants");
}

export function getOracleForecast(merchantId: string, horizonDays = 60) {
  return j<OracleForecast>("/oracle/forecast", {
    method: "POST",
    body: JSON.stringify({ merchant_id: merchantId, horizon_days: horizonDays }),
  });
}

export function getOraclePeers(merchantId: string) {
  return j<PeerComparison>(`/oracle/peers/${merchantId}`);
}

export function getOracleAnomalies(merchantId: string, lookbackDays = 30) {
  return j<AnomalyFeed>(`/oracle/anomalies/${merchantId}?lookback_days=${lookbackDays}`);
}

export function getOracleFingerprint(merchantId: string) {
  return j<Fingerprint>(`/oracle/fingerprint/${merchantId}`);
}

export function runOracleScenario(body: {
  merchant_id: string;
  shock_type: ShockType;
  shock_magnitude: number;
  shock_start_date: string;
  shock_duration_days: number;
  horizon_days?: number;
}) {
  return j<ScenarioResult>("/oracle/scenario", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getOracleLLMRecommendation(body: {
  merchant_id: string;
  forecast: OracleForecast;
  regime?: string;
  regime_confidence?: number;
  peer_comparison?: PeerComparison;
  anomaly_flag?: boolean;
  anomaly_explanation?: string | null;
  carry_cost_analysis?: OracleForecast["carry_cost_analysis"];
  credit_apply_by_date?: string | null;
}) {
  return j<LLMRecommendation>("/oracle/llm_recommendation", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getOracleAlertPreview(merchantId: string) {
  return j<AlertPreview>("/oracle/alert_preview", {
    method: "POST",
    body: JSON.stringify({ merchant_id: merchantId }),
  });
}

// ---- shared formatting ----
export function inr(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const x = Number(n);
  if (Math.abs(x) >= 1e7) return `₹${(x / 1e7).toFixed(2)}Cr`;
  if (Math.abs(x) >= 1e5) return `₹${(x / 1e5).toFixed(2)}L`;
  return `₹${x.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function shortDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}
