"use client";

import { useEffect, useState } from "react";
import { getSegmentStats } from "@/lib/api";
import { inr } from "@/lib/profiles";
import type { SegmentStats } from "@/lib/types";
import { ConversionCurve } from "./ConversionCurve";

const PRESET_SEGMENTS = [
  "1|iPhone|Credit_Card",
  "2|Android_premium|UPI",
  "3|Android_budget|COD",
];

export function SegmentExplorer({ seedSegment }: { seedSegment?: string }) {
  const [segment, setSegment] = useState(seedSegment || PRESET_SEGMENTS[0]);
  const [data, setData] = useState<SegmentStats | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (seedSegment) setSegment(seedSegment);
  }, [seedSegment]);

  useEffect(() => {
    let alive = true;
    getSegmentStats(segment)
      .then((d) => alive && (setData(d), setErr(null)))
      .catch((e) => alive && setErr(e.message));
    return () => {
      alive = false;
    };
  }, [segment]);

  const post = data?.posterior;
  const rev = data?.revenue_simulation;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink">
          Segment confidence intervals
        </h2>
        <div className="flex items-center gap-2">
          <select
            className="rounded border border-slate-200 px-2 py-1 text-xs"
            value={segment}
            onChange={(e) => setSegment(e.target.value)}
          >
            {[...new Set([segment, ...PRESET_SEGMENTS])].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>

      {err && <p className="text-xs text-red-600">{err}</p>}
      {!data ? (
        <p className="text-xs text-slate-400">loading…</p>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          <div className="space-y-3">
            <div className="rounded-lg bg-slate-50 p-3">
              <p className="text-[11px] text-slate-500">
                Bayesian posterior WTP (Normal-Normal, {data.n_observations} obs)
              </p>
              <p className="mt-1 text-2xl font-bold text-brand-dark">
                ×{post?.mean_wtp.toFixed(3)}
              </p>
              <p className="text-[11px] text-slate-500">
                95% CI [{post?.ci_95[0].toFixed(3)} – {post?.ci_95[1].toFixed(3)}]
                {" · "}prior ×{data.prior.mean.toFixed(2)}
                {data.observed.mean_wtp != null &&
                  ` · observed ×${data.observed.mean_wtp.toFixed(3)}`}
              </p>
              <CiBar
                lo={post!.ci_95[0]}
                mean={post!.mean_wtp}
                hi={post!.ci_95[1]}
              />
            </div>
            <div className="rounded-lg bg-slate-50 p-3 text-xs">
              <p className="text-slate-500">
                {data.n_customers_like_this} customers like this seen
              </p>
              {rev && (
                <>
                  <p className="mt-1">
                    Expected gross margin — WTP{" "}
                    <strong>{inr(rev.expected_margin_wtp_pricing ?? 0)}</strong> vs
                    flat <strong>{inr(rev.expected_margin_flat_pricing ?? 0)}</strong>
                  </p>
                  <p
                    className={`mt-0.5 font-medium ${
                      rev.pct_lift >= 0 ? "text-brand-dark" : "text-amber-700"
                    }`}
                  >
                    {rev.pct_lift >= 0 ? "+" : ""}
                    {rev.pct_lift.toFixed(1)}% margin lift
                    {typeof rev.revenue_pct_lift === "number" && (
                      <span className="text-slate-400">
                        {" "}· revenue {rev.revenue_pct_lift >= 0 ? "+" : ""}
                        {rev.revenue_pct_lift.toFixed(1)}%
                      </span>
                    )}
                  </p>
                  <p className="text-[10px] text-slate-400">
                    assumes {((rev.gross_margin_assumption ?? 0.45) * 100).toFixed(0)}%
                    gross margin
                  </p>
                </>
              )}
            </div>
          </div>
          <div>
            <p className="mb-1 text-[11px] text-slate-500">
              Conversion probability across price points
            </p>
            <ConversionCurve curve={data.conversion_curve} />
          </div>
        </div>
      )}
    </section>
  );
}

function CiBar({ lo, mean, hi }: { lo: number; mean: number; hi: number }) {
  const min = 0.85;
  const max = 1.25;
  const pct = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <div className="relative mt-2 h-6">
      <div className="absolute left-0 right-0 top-1/2 h-1 -translate-y-1/2 rounded bg-slate-200" />
      <div
        className="absolute top-1/2 h-1 -translate-y-1/2 rounded bg-brand/40"
        style={{ left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%` }}
      />
      <div
        className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand"
        style={{ left: `${pct(mean)}%` }}
      />
      <span className="absolute left-0 top-full text-[9px] text-slate-400">
        {min}
      </span>
      <span className="absolute right-0 top-full text-[9px] text-slate-400">
        {max}
      </span>
    </div>
  );
}
