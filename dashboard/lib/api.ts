import type { CustomerSignals, MetricsResponse, PricingResponse } from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

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

export function personalize(signals: CustomerSignals) {
  return jsonFetch<PricingResponse>("/personalize", {
    method: "POST",
    body: JSON.stringify(signals),
  });
}

export function simulate(profile: CustomerSignals) {
  return jsonFetch<{ base: PricingResponse; sensitivity: any[] }>("/simulate", {
    method: "POST",
    body: JSON.stringify({ profile }),
  });
}

export function getMetrics() {
  return jsonFetch<MetricsResponse>("/metrics");
}

export function getHealth() {
  return jsonFetch<Record<string, any>>("/health");
}

export const API_BASE = BASE;
