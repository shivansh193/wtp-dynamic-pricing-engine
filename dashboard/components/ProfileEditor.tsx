"use client";

import type { CustomerSignals } from "@/lib/types";
import { IP_SAMPLES } from "@/lib/profiles";

const DEVICES = ["Android_budget", "Android_premium", "iPhone", "Desktop"] as const;
const PAYMENTS = ["UPI", "Credit_Card", "Debit_Card", "COD", "Wallet"] as const;
const IP_TYPES = [
  "residential",
  "mobile_carrier",
  "public_wifi",
  "vpn",
  "datacenter",
  "tor",
] as const;

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-xs text-slate-500">{label}</span>
      <div className="flex items-center gap-2">{children}</div>
    </label>
  );
}

export function ProfileEditor({
  which,
  profile,
  latencyMs,
  onChange,
}: {
  which: "A" | "B";
  profile: CustomerSignals;
  latencyMs: number | null;
  onChange: (patch: Partial<CustomerSignals>) => void;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-semibold text-ink">
          Profile editor — Customer {which}
        </p>
        {latencyMs != null && (
          <span className="text-[10px] text-slate-400">
            last /personalize: {latencyMs.toFixed(1)} ms
          </span>
        )}
      </div>

      <Row label="Device">
        <select
          className="rounded border border-slate-200 px-2 py-1 text-xs"
          value={profile.device_type}
          onChange={(e) => onChange({ device_type: e.target.value as any })}
        >
          {DEVICES.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </Row>

      <Row label={`City tier: ${profile.city_tier}`}>
        <input
          type="range"
          min={1}
          max={3}
          step={1}
          value={profile.city_tier}
          onChange={(e) =>
            onChange({ city_tier: Number(e.target.value) as 1 | 2 | 3 })
          }
        />
      </Row>

      <Row label="Payment preference">
        <select
          className="rounded border border-slate-200 px-2 py-1 text-xs"
          value={profile.payment_method_preference}
          onChange={(e) =>
            onChange({ payment_method_preference: e.target.value as any })
          }
        >
          {PAYMENTS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </Row>

      <Row label={`Trust score: ${profile.cross_merchant_trust_score}`}>
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={profile.cross_merchant_trust_score}
          onChange={(e) =>
            onChange({ cross_merchant_trust_score: Number(e.target.value) })
          }
        />
      </Row>

      <Row label={`Return rate: ${(profile.return_rate * 100).toFixed(0)}%`}>
        <input
          type="range"
          min={0}
          max={0.8}
          step={0.01}
          value={profile.return_rate}
          onChange={(e) => onChange({ return_rate: Number(e.target.value) })}
        />
      </Row>

      <Row
        label={`Account age: ${Math.round(profile.account_age_days / 30)} mo`}
      >
        <input
          type="range"
          min={1}
          max={1800}
          step={10}
          value={profile.account_age_days}
          onChange={(e) =>
            onChange({ account_age_days: Number(e.target.value) })
          }
        />
      </Row>

      <Row label="IP type / sample IP">
        <select
          className="rounded border border-slate-200 px-2 py-1 text-xs"
          value={profile.ip_type ?? "residential"}
          onChange={(e) => {
            const t = e.target.value;
            onChange({ ip_type: t, ip: IP_SAMPLES[t] ?? profile.ip });
          }}
        >
          {IP_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </Row>
    </div>
  );
}
