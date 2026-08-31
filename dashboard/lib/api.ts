import type {
  AbTestResult,
  FunnelResult,
  CustomSessionFields,
  CustomerSignals,
  MerchantConfig,
  MetricsResponse,
  Preset,
  PricingResponse,
  SegmentStats,
  SessionCreateResponse,
  SessionInfo,
} from "./types";

const BASE = (
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

export const API_BASE = BASE;

/** ws:// or wss:// origin for the live session feed. */
export function wsBase(): string {
  try {
    const u = new URL(BASE);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    return u.toString().replace(/\/$/, "");
  } catch {
    return BASE.replace(/^http/, "ws");
  }
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return (await res.json()) as T;
}

// ---- pricing ----
export function personalize(signals: Partial<CustomerSignals> & { list_price: number }) {
  return jsonFetch<PricingResponse>("/personalize", {
    method: "POST",
    body: JSON.stringify(signals),
  });
}

export function simulate(profile: Partial<CustomerSignals> & { list_price: number }) {
  return jsonFetch<{ base: PricingResponse; sensitivity: any[] }>("/simulate", {
    method: "POST",
    body: JSON.stringify({ profile }),
  });
}

export function getMetrics() {
  return jsonFetch<MetricsResponse>("/metrics");
}

export function runAbTest(body: {
  segment: Record<string, unknown>;
  sample_size?: number;
  seed?: number;
}) {
  return jsonFetch<AbTestResult>("/simulate/ab_test", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getFunnel() {
  return jsonFetch<FunnelResult>("/funnel");
}

export function getHealth() {
  return jsonFetch<Record<string, any>>("/health");
}

// ---- link-generator demo flow ----
export function createSession(preset: Preset, custom?: CustomSessionFields, seed?: number) {
  return jsonFetch<SessionCreateResponse>("/session/create", {
    method: "POST",
    body: JSON.stringify({ preset, custom, seed }),
  });
}

export function getSession(sessionId: string) {
  return jsonFetch<SessionInfo>(`/session/${sessionId}`);
}

export function deriveConfig(knobs: {
  pin_code?: string;
  device_type?: string;
  payment_method_preference?: string;
  payment_split?: Record<string, number>;
  prepaid_orders?: number;
  return_rate?: number;
  vpn?: boolean;
}) {
  return jsonFetch<{ config: SessionInfo["config"]; segment_key: string }>(
    "/config/derive",
    { method: "POST", body: JSON.stringify(knobs) },
  );
}

export function getDecision(sessionId: string) {
  return jsonFetch<{
    session_id: string;
    decision_count: number;
    decisions: any[];
  }>(`/decision/${sessionId}`);
}

export function getAllSessions() {
  return jsonFetch<{ count: number; backend: string; sessions: SessionInfo[] }>(
    "/sessions/all",
  );
}

export function completeSession(sessionId: string) {
  return jsonFetch<SessionInfo>(`/session/${sessionId}/complete`, { method: "POST" });
}

export function getSegmentStats(segmentKey: string) {
  return jsonFetch<SegmentStats>(`/segment/stats/${encodeURIComponent(segmentKey)}`);
}

// ---- merchant pricing rules ----
export function getMerchantConfig() {
  return jsonFetch<MerchantConfig>("/merchant/config");
}

export function updateMerchantConfig(patch: Partial<MerchantConfig>) {
  return jsonFetch<MerchantConfig>("/merchant/config", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export function resetMerchantConfig() {
  return jsonFetch<MerchantConfig>("/merchant/config/reset", { method: "POST" });
}
