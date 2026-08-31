"use client";

import { useEffect, useState } from "react";
import { getInterventionPerformance } from "@/lib/api";
import { inr } from "@/lib/profiles";
import type { InterventionPerformance as Perf } from "@/lib/types";

const FRICTION_LABEL: Record<string, string> = {
  price_sensitivity: "Price sensitivity",
  trust_deficit: "Trust deficit",
  decision_paralysis: "Decision paralysis",
  payment_friction: "Payment friction",
  delivery_anxiety: "Delivery anxiety",
  urgency_insensitive: "Urgency-insensitive",
  unknown: "Unclassified",
};

/** Which interventions actually convert, once sessions settle. Backed by
 *  GET /interventions/performance (intervention_events log + fatigue). */
export function InterventionPerformance() {
  const [data, setData] = useState<Perf | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setBusy(true);
    getInterventionPerformance()
      .then((d) => {
        setData(d);
        setErr(null);
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setBusy(false));
  };
  useEffect(load, []);

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-800">
          Intervention performance
          <span className="ml-2 font-normal text-zinc-400">
            conversion &amp; revenue by intervention
          </span>
        </h2>
        <div className="flex items-center gap-3 text-[11px] text-zinc-400">
          {data && (
            <span>
              {data.n_events.toLocaleString()} shown · {data.n_settled.toLocaleString()}{" "}
              settled
              {data.baseline_conversion != null &&
                ` · baseline ${(data.baseline_conversion * 100).toFixed(1)}%`}
            </span>
          )}
          <button onClick={load} disabled={busy} className="hover:text-zinc-600">
            {busy ? "…" : "↻"}
          </button>
        </div>
      </div>

      {err && <p className="text-xs text-red-600">{err}</p>}
      {!data ? (
        <p className="text-xs text-zinc-400">loading…</p>
      ) : data.n_events === 0 ? (
        <p className="text-xs text-zinc-400">{data.note}</p>
      ) : (
        <div className="space-y-5">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase tracking-wide text-zinc-400">
                <tr className="[&_th]:px-2 [&_th]:py-1 [&_th]:text-left">
                  <th>Intervention</th>
                  <th>Targets</th>
                  <th className="!text-right">Shown</th>
                  <th className="!text-right">Conv.</th>
                  <th className="!text-right">vs base</th>
                  <th className="!text-right">Rev / shown</th>
                </tr>
              </thead>
              <tbody className="[&_td]:px-2 [&_td]:py-1">
                {data.by_intervention.map((r) => (
                  <tr key={r.intervention_id} className="border-t border-zinc-100">
                    <td className="font-medium text-zinc-700">
                      {r.intervention_id.replace(/_/g, " ")}
                      {r.slot && (
                        <span className="ml-1 text-[10px] text-zinc-400">
                          {r.slot}
                        </span>
                      )}
                    </td>
                    <td className="text-zinc-500">
                      {FRICTION_LABEL[r.friction_type ?? "unknown"] ??
                        r.friction_type}
                    </td>
                    <td className="text-right tabular-nums">{r.times_shown}</td>
                    <td className="text-right tabular-nums">
                      {r.conversion_rate == null
                        ? "—"
                        : `${(r.conversion_rate * 100).toFixed(1)}%`}
                    </td>
                    <td
                      className={`text-right tabular-nums ${
                        (r.lift_vs_baseline ?? 0) > 0
                          ? "text-emerald-600"
                          : (r.lift_vs_baseline ?? 0) < 0
                            ? "text-amber-700"
                            : "text-zinc-400"
                      }`}
                    >
                      {r.lift_vs_baseline == null
                        ? "—"
                        : `${r.lift_vs_baseline >= 0 ? "+" : ""}${(
                            r.lift_vs_baseline * 100
                          ).toFixed(1)} pts`}
                    </td>
                    <td className="text-right tabular-nums">
                      {inr(r.revenue_per_shown)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg bg-zinc-50 p-3 text-xs">
              <p className="mb-1 text-zinc-500">Common friction by category</p>
              <ul className="space-y-1">
                {Object.entries(data.frictions_by_category).map(([cat, list]) => (
                  <li key={cat}>
                    <span className="font-medium text-zinc-600">{cat}</span>
                    {": "}
                    <span className="text-zinc-500">
                      {list
                        .slice(0, 3)
                        .map(
                          (f) =>
                            `${FRICTION_LABEL[f.friction_type] ?? f.friction_type} ${(
                              f.share * 100
                            ).toFixed(0)}%`,
                        )
                        .join(" · ")}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-lg bg-zinc-50 p-3 text-xs">
              <p className="mb-1 text-zinc-500">
                Fatigued ({data.fatigue_threshold ?? 3}+ shows, 0 conversions →
                rotated out)
              </p>
              {data.fatigued_pairs.length === 0 ? (
                <p className="text-zinc-400">none yet</p>
              ) : (
                <ul className="space-y-1">
                  {data.fatigued_pairs.slice(0, 6).map((p, i) => (
                    <li key={i} className="text-zinc-600">
                      <span className="font-mono text-[11px] text-zinc-500">
                        {p.segment_key}
                      </span>{" "}
                      → {p.intervention_id.replace(/_/g, " ")} ({p.times_shown}×)
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <p className="text-[10px] leading-relaxed text-zinc-400">{data.note}</p>
        </div>
      )}
    </section>
  );
}
