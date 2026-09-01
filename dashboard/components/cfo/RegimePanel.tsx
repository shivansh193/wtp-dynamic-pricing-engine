"use client";

import type { OracleForecast } from "@/lib/cfoTypes";
import { shortDate } from "@/lib/cfoApi";

const REGIME_STYLE: Record<
  string,
  { label: string; badge: string; bar: string }
> = {
  high_season: {
    label: "HIGH SEASON",
    badge: "bg-emerald-100 text-emerald-800 ring-emerald-300",
    bar: "#10b981",
  },
  low_season: {
    label: "LOW SEASON",
    badge: "bg-amber-100 text-amber-800 ring-amber-300",
    bar: "#f59e0b",
  },
  stress: {
    label: "STRESS",
    badge: "bg-red-100 text-red-800 ring-red-300",
    bar: "#ef4444",
  },
};

export function RegimePanel({ f }: { f: OracleForecast }) {
  const s = REGIME_STYLE[f.regime] ?? REGIME_STYLE.low_season;
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="mb-3 text-[13px] font-semibold text-zinc-800">
        Current regime
      </h2>
      <div className="flex items-center gap-3">
        <span
          className={`rounded-md px-3 py-1.5 text-sm font-bold tracking-wide ring-1 ${s.badge}`}
        >
          {s.label}
        </span>
        <span className="text-xs text-zinc-500">
          {(f.regime_confidence * 100).toFixed(0)}% confidence
        </span>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-zinc-600">
        {f.regime_description}
      </p>

      <p className="mt-4 mb-1 text-[10px] uppercase tracking-wide text-zinc-400">
        Last 90 days
      </p>
      <div className="flex h-6 w-full overflow-hidden rounded">
        {f.regime_history.map((h, i) => (
          <span
            key={i}
            title={`${shortDate(h.date)} · ${h.regime}`}
            style={{
              flex: 1,
              background: (REGIME_STYLE[h.regime] ?? REGIME_STYLE.low_season).bar,
            }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[9px] text-zinc-400">
        <span>{f.regime_history[0] && shortDate(f.regime_history[0].date)}</span>
        <span>
          {f.regime_history.at(-1) && shortDate(f.regime_history.at(-1)!.date)}
        </span>
      </div>

      <div className="mt-3 flex gap-3 text-[10px] text-zinc-500">
        {Object.entries(REGIME_STYLE).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: v.bar }}
            />
            {v.label.toLowerCase()}
          </span>
        ))}
      </div>
    </section>
  );
}
