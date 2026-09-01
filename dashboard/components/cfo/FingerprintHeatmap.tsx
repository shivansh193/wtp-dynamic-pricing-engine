"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getOracleFingerprint, inr } from "@/lib/cfoApi";
import type { Fingerprint } from "@/lib/cfoTypes";
import { PanelSkeleton, ErrorNote } from "./Skeleton";

// approx ISO week of the main festivals (current calendar year, good enough)
const FESTIVAL_WEEK: Record<string, number> = {
  Diwali: 45,
  Holi: 10,
  Eid: 12,
  Christmas: 52,
};
const CURVE_COLOR: Record<string, string> = {
  Diwali: "#d97706",
  Holi: "#db2777",
  Eid: "#0891b2",
  Christmas: "#059669",
};

function heat(v: number | null): string {
  if (v == null) return "#f4f4f5";
  // light -> dark indigo
  const t = Math.max(0, Math.min(1, v));
  const l = 96 - t * 62;
  return `hsl(243 65% ${l}%)`;
}

export function FingerprintHeatmap({ merchantId }: { merchantId: string }) {
  const [fp, setFp] = useState<Fingerprint | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null);

  const load = () => {
    setErr(null);
    setFp(null);
    getOracleFingerprint(merchantId)
      .then(setFp)
      .catch((e) => setErr((e as Error).message));
  };
  useEffect(load, [merchantId]);

  const curveData = useMemo(() => {
    if (!fp) return [];
    const { weeks_offset, curves } = fp.festival_response_curves;
    return weeks_offset.map((o, i) => {
      const row: Record<string, number | string | null> = {
        offset: o === 0 ? "festival" : `${o > 0 ? "+" : ""}${o}w`,
      };
      for (const [name, arr] of Object.entries(curves)) row[name] = arr[i];
      return row;
    });
  }, [fp]);

  if (err) return <ErrorNote error={err} onRetry={load} />;
  if (!fp) return <PanelSkeleton chart lines={2} />;

  const m = fp.fingerprint;
  const festByWeek: Record<number, string> = {};
  for (const [name, wk] of Object.entries(FESTIVAL_WEEK)) festByWeek[wk] = name;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="mb-3 text-[13px] font-semibold text-zinc-800">
        Your settlement pattern
      </h2>

      <div className="overflow-x-auto">
        <div className="inline-block">
          <div className="flex">
            <div className="w-8" />
            <div className="flex gap-[1px]">
              {Array.from({ length: 52 }).map((_, c) => (
                <div
                  key={c}
                  className="w-[7px] text-center text-[7px] text-zinc-400"
                >
                  {festByWeek[c + 1] ? "▾" : (c + 1) % 13 === 0 ? c + 1 : ""}
                </div>
              ))}
            </div>
          </div>
          {m.matrix.map((row, r) => (
            <div key={r} className="flex items-center">
              <div className="w-8 pr-1 text-right text-[8px] text-zinc-400">
                {m.weekday_labels[r]}
              </div>
              <div className="flex gap-[1px]">
                {row.map((v, c) => (
                  <div
                    key={c}
                    onMouseEnter={() => setHover({ r, c })}
                    onMouseLeave={() => setHover(null)}
                    className="h-[10px] w-[7px] rounded-[1px]"
                    style={{ background: heat(v) }}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-2 h-8 text-[11px] text-zinc-500">
        {hover ? (
          <>
            Week {hover.c + 1}, {m.weekday_labels[hover.r]} — avg{" "}
            {inr(m.raw_inr[hover.r][hover.c])}
            {festByWeek[hover.c + 1] && (
              <span className="ml-1 text-amber-600">
                · {festByWeek[hover.c + 1]} week
              </span>
            )}
          </>
        ) : (
          <span className="text-zinc-400">
            Hover a cell · darker = higher settlement volume · ▾ marks festival weeks
          </span>
        )}
      </div>

      <p className="mt-3 mb-1 text-[11px] font-medium text-zinc-600">
        Festival response — settlement multiplier vs the yearly weekly average
      </p>
      <ResponsiveContainer width="100%" height={170}>
        <LineChart data={curveData} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="offset" tick={{ fontSize: 10 }} />
          <YAxis
            tick={{ fontSize: 10 }}
            width={34}
            tickFormatter={(v) => `${v}x`}
          />
          <Tooltip formatter={(v: number) => `${v?.toFixed?.(2)}x`} />
          <ReferenceLine y={1} stroke="#a1a1aa" strokeDasharray="3 3" />
          {Object.keys(fp.festival_response_curves.curves).map((name) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={CURVE_COLOR[name] ?? "#4f46e5"}
              strokeWidth={2}
              dot={{ r: 2 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-1 flex gap-3 text-[10px] text-zinc-500">
        {Object.keys(fp.festival_response_curves.curves).map((name) => (
          <span key={name} className="flex items-center gap-1">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: CURVE_COLOR[name] ?? "#4f46e5" }}
            />
            {name}
          </span>
        ))}
      </div>
    </section>
  );
}
