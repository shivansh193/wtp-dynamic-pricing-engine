"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from "recharts";
import { getOraclePeers, inr } from "@/lib/cfoApi";
import type { PeerComparison, PeerMetric } from "@/lib/cfoTypes";
import { PanelSkeleton, ErrorNote } from "./Skeleton";

export function PeerBenchmarking({ merchantId }: { merchantId: string }) {
  const [p, setP] = useState<PeerComparison | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    setErr(null);
    setP(null);
    getOraclePeers(merchantId)
      .then(setP)
      .catch((e) => setErr((e as Error).message));
  };
  useEffect(load, [merchantId]);

  if (err) return <ErrorNote error={err} onRetry={load} />;
  if (!p) return <PanelSkeleton chart lines={2} />;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-800">
          How do you compare?
        </h2>
        <span className="text-[10px] text-zinc-400">
          {p.n_peers} peers · {p.peer_group}
        </span>
      </div>

      <div className="mt-3 grid gap-5 sm:grid-cols-2">
        <Dist
          title="Settlement volatility"
          metric={p.volatility}
          fmt={(v) => v.toFixed(3)}
        />
        <Dist
          title="Average daily settlement"
          metric={p.avg_daily_settlement}
          fmt={(v) => inr(v)}
        />
      </div>

      {p.stress_frequency && (
        <p className="mt-4 rounded-md bg-zinc-50 px-3 py-2 text-xs text-zinc-600">
          {p.stress_frequency.plain}
        </p>
      )}
    </section>
  );
}

function Dist({
  title,
  metric,
  fmt,
}: {
  title: string;
  metric: PeerMetric;
  fmt: (v: number) => string;
}) {
  // histogram: bucket the peer distribution, mark the merchant's bucket
  const vals = [...metric.distribution, metric.you];
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const bins = 8;
  const width = (hi - lo) / bins || 1;
  const counts = Array.from({ length: bins }, () => 0);
  for (const v of metric.distribution) {
    const idx = Math.min(bins - 1, Math.floor((v - lo) / width));
    counts[idx] += 1;
  }
  const youBin = Math.min(bins - 1, Math.floor((metric.you - lo) / width));
  const data = counts.map((c, i) => ({
    bin: fmt(lo + (i + 0.5) * width),
    count: c,
    you: i === youBin,
  }));

  return (
    <div>
      <p className="mb-1 text-[11px] font-medium text-zinc-600">{title}</p>
      <ResponsiveContainer width="100%" height={110}>
        <BarChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
          <XAxis dataKey="bin" tick={{ fontSize: 8 }} interval={1} />
          <Tooltip
            formatter={(v: number, _n, ctx: any) =>
              ctx?.payload?.you ? `${v} peers · you are here` : `${v} peers`
            }
          />
          <Bar dataKey="count" radius={[2, 2, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.you ? "#4f46e5" : "#d4d4d8"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-1 text-[11px] text-zinc-600">{metric.plain}</p>
      <p className="text-[10px] text-zinc-400">
        you {fmt(metric.you)} · peer avg{" "}
        {metric.peer_avg != null ? fmt(metric.peer_avg) : "—"}
      </p>
    </div>
  );
}
