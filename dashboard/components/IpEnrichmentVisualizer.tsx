"use client";

import type { PricingResponse } from "@/lib/types";

const TRUST_SCALE: { type: string; mult: number }[] = [
  { type: "residential", mult: 1.0 },
  { type: "mobile_carrier", mult: 0.95 },
  { type: "unknown", mult: 0.8 },
  { type: "public_wifi", mult: 0.7 },
  { type: "vpn", mult: 0.6 },
  { type: "datacenter", mult: 0.5 },
  { type: "tor", mult: 0.3 },
];

export function IpEnrichmentVisualizer({
  label,
  result,
  vpnOn,
  onToggleVpn,
}: {
  label: string;
  result: PricingResponse | null;
  vpnOn: boolean;
  onToggleVpn: (on: boolean) => void;
}) {
  const e = result?.ip_enrichment;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-ink">IP enrichment — {label}</p>
        <label className="flex items-center gap-2 text-xs text-slate-500">
          VPN mode
          <button
            role="switch"
            aria-checked={vpnOn}
            onClick={() => onToggleVpn(!vpnOn)}
            className={`relative h-5 w-9 rounded-full transition ${
              vpnOn ? "bg-brand" : "bg-slate-300"
            }`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition ${
                vpnOn ? "left-4" : "left-0.5"
              }`}
            />
          </button>
        </label>
      </div>

      {!e ? (
        <p className="text-xs text-slate-400">waiting for a decision…</p>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <Info k="Detected type" v={e.ip_type} />
            <Info k="Trust multiplier" v={`x${e.ip_trust_multiplier.toFixed(2)}`} />
            <Info
              k="Whitelist"
              v={e.is_whitelisted ? "yes (Indian shared IP)" : "no"}
              good={e.is_whitelisted}
            />
            <Info
              k="Blocklist"
              v={e.blocklist_hits.length ? e.blocklist_hits.join(", ") : "clean"}
              bad={e.blocklist_hits.length > 0}
            />
            <Info k="Geo source" v={e.geo_source} />
            <Info
              k="Location confidence"
              v={`${(e.location_confidence * 100).toFixed(0)}%`}
            />
            <Info k="Cache" v={e.cache_hit ? "hit" : "miss"} />
            <Info k="Lookup" v={`${e.lookup_ms.toFixed(2)} ms`} />
          </div>

          {/* trust scale */}
          <div>
            <p className="mb-1 text-[10px] font-medium text-slate-400">
              trust multiplier by network type
            </p>
            <div className="flex overflow-hidden rounded">
              {TRUST_SCALE.map((s) => (
                <div
                  key={s.type}
                  className={`flex-1 py-1 text-center text-[9px] ${
                    s.type === e.ip_type
                      ? "bg-brand text-white"
                      : "bg-slate-100 text-slate-400"
                  }`}
                  title={`${s.type}: x${s.mult}`}
                >
                  {s.mult}
                </div>
              ))}
            </div>
          </div>

          {result && (
            <p className="text-[11px] text-slate-500">
              → checkout shows{" "}
              <strong>
                ₹
                {result.final_price.toLocaleString("en-IN", {
                  maximumFractionDigits: 0,
                })}
              </strong>{" "}
              ({result.price_delta_pct >= 0 ? "+" : ""}
              {result.price_delta_pct.toFixed(1)}%), offer{" "}
              <strong>{result.offer_type}</strong>, COD{" "}
              {result.cod_eligible ? "on" : "off"}. Toggling VPN re-runs{" "}
              <code>/personalize</code> and applies the multiplier to the
              cross-merchant trust score.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Info({
  k,
  v,
  good,
  bad,
}: {
  k: string;
  v: string;
  good?: boolean;
  bad?: boolean;
}) {
  return (
    <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1">
      <span className="block text-[10px] uppercase tracking-wide text-slate-400">
        {k}
      </span>
      <span
        className={`font-medium ${
          good ? "text-emerald-600" : bad ? "text-red-600" : "text-slate-700"
        }`}
      >
        {v}
      </span>
    </div>
  );
}
