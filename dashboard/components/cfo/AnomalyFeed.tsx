"use client";

import { useEffect, useState } from "react";
import { getOracleAnomalies, inr, shortDate } from "@/lib/cfoApi";
import type { AnomalyFeed as Feed } from "@/lib/cfoTypes";
import { PanelSkeleton, ErrorNote } from "./Skeleton";

export function AnomalyFeed({ merchantId }: { merchantId: string }) {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    setErr(null);
    setFeed(null);
    getOracleAnomalies(merchantId, 30)
      .then(setFeed)
      .catch((e) => setErr((e as Error).message));
  };
  useEffect(load, [merchantId]);

  if (err) return <ErrorNote error={err} onRetry={load} />;
  if (!feed) return <PanelSkeleton lines={4} />;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-800">
          Recent anomalies
        </h2>
        <span className="text-[10px] text-zinc-400">
          last {feed.lookback_days}d · &gt;{feed.sigma_threshold}σ
        </span>
      </div>

      {feed.anomalies.length === 0 ? (
        <p className="flex items-center gap-2 text-xs text-emerald-700">
          <span className="text-base">✓</span> No anomalies detected in the last 30
          days.
        </p>
      ) : (
        <ul className="space-y-2">
          {feed.anomalies.map((a, i) => {
            const spike = a.kind === "SPIKE";
            return (
              <li
                key={i}
                className="flex gap-3 border-l-2 pl-3 text-xs"
                style={{ borderColor: spike ? "#10b981" : "#ef4444" }}
              >
                <div className="w-14 shrink-0 text-zinc-400">
                  {shortDate(a.date)}
                </div>
                <div className="flex-1">
                  <span
                    className={`mr-1 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      spike
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    {a.kind}
                  </span>
                  <span className="tabular-nums text-zinc-500">
                    {a.magnitude_sigma > 0 ? "+" : ""}
                    {a.magnitude_sigma}σ
                  </span>
                  <span className="ml-1 text-zinc-400">
                    ({inr(a.actual_inr)} vs {inr(a.expected_inr)} expected)
                  </span>
                  <p className="mt-0.5 text-zinc-600">{a.explanation}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
