"use client";

import { useMemo, useState } from "react";
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
import { runOracleScenario, inr, shortDate } from "@/lib/cfoApi";
import type { ScenarioResult, ShockType } from "@/lib/cfoTypes";
import { ErrorNote } from "./Skeleton";

const SHOCKS: { type: ShockType; label: string; emoji: string }[] = [
  { type: "discount_sale", label: "Run a discount sale", emoji: "🏷️" },
  { type: "marketing_spend", label: "Increase marketing spend", emoji: "📣" },
  { type: "inventory_purchase", label: "Buy more inventory", emoji: "📦" },
  { type: "payment_gateway_outage", label: "Payment gateway outage", emoji: "⚠️" },
];

function isoPlusDays(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export function ScenarioSimulator({ merchantId }: { merchantId: string }) {
  const [shock, setShock] = useState<ShockType | null>(null);
  const [magnitude, setMagnitude] = useState(20);
  const [start, setStart] = useState(isoPlusDays(14));
  const [duration, setDuration] = useState(10);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<ScenarioResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const minStart = isoPlusDays(7);
  const maxStart = isoPlusDays(30);

  const simulate = async () => {
    if (!shock) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await runOracleScenario({
        merchant_id: merchantId,
        shock_type: shock,
        shock_magnitude: magnitude,
        shock_start_date: start,
        shock_duration_days: duration,
      });
      setRes(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const chartData = useMemo(() => {
    if (!res) return [];
    return res.forecast_dates.map((d, i) => ({
      date: d,
      original: res.original_forecast_curve[i]?.balance ?? null,
      shocked: res.shocked_forecast_curve[i]?.balance ?? null,
    }));
  }, [res]);

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="mb-3 text-[13px] font-semibold text-zinc-800">What if?</h2>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {SHOCKS.map((s) => (
          <button
            key={s.type}
            onClick={() => setShock(s.type)}
            className={`rounded-md border px-3 py-2 text-left text-xs ${
              shock === s.type
                ? "border-brand bg-brand/5 font-medium text-brand-dark"
                : "border-zinc-200 text-zinc-600 hover:bg-zinc-50"
            }`}
          >
            <span className="mr-1">{s.emoji}</span>
            {s.label}
          </button>
        ))}
      </div>

      {shock && (
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <label className="block text-xs">
            <span className="text-zinc-500">
              Magnitude: <strong>{magnitude}%</strong>
            </span>
            <input
              type="range"
              min={5}
              max={50}
              step={5}
              value={magnitude}
              onChange={(e) => setMagnitude(+e.target.value)}
              className="mt-1 w-full accent-brand"
            />
          </label>
          <label className="block text-xs">
            <span className="text-zinc-500">Start date</span>
            <input
              type="date"
              min={minStart}
              max={maxStart}
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 px-2 py-1"
            />
          </label>
          <label className="block text-xs">
            <span className="text-zinc-500">
              Duration: <strong>{duration} days</strong>
            </span>
            <input
              type="range"
              min={3}
              max={21}
              value={duration}
              onChange={(e) => setDuration(+e.target.value)}
              className="mt-1 w-full accent-brand"
            />
          </label>
        </div>
      )}

      <button
        onClick={simulate}
        disabled={!shock || busy}
        className="mt-4 rounded-md bg-zinc-900 px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
      >
        {busy ? "Simulating…" : "Simulate"}
      </button>

      {err && <div className="mt-3"><ErrorNote error={err} onRetry={simulate} /></div>}

      {res && (
        <div className="mt-5 space-y-3">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickFormatter={shortDate}
                minTickGap={28}
              />
              <YAxis
                tick={{ fontSize: 10 }}
                width={52}
                tickFormatter={(v) => inr(v).replace("₹", "")}
              />
              <Tooltip
                formatter={(v: number) => inr(v)}
                labelFormatter={(l) => shortDate(l as string)}
              />
              <ReferenceLine
                y={res.operating_threshold}
                stroke="#dc2626"
                strokeDasharray="5 4"
              />
              <Line
                type="monotone"
                dataKey="original"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
                name="original"
              />
              <Line
                type="monotone"
                dataKey="shocked"
                stroke="#ea580c"
                strokeWidth={2}
                dot={false}
                name="with scenario"
              />
            </LineChart>
          </ResponsiveContainer>

          <div className="flex flex-wrap gap-4 text-xs">
            <span>
              End-of-horizon cash:{" "}
              <strong
                className={
                  res.delta_cash_position_final_inr >= 0
                    ? "text-emerald-600"
                    : "text-amber-700"
                }
              >
                {res.delta_cash_position_final_inr >= 0 ? "+" : ""}
                {inr(res.delta_cash_position_final_inr)}
              </strong>
            </span>
            <span>
              Worst-point cash:{" "}
              <strong
                className={
                  res.delta_min_balance_inr >= 0
                    ? "text-emerald-600"
                    : "text-amber-700"
                }
              >
                {res.delta_min_balance_inr >= 0 ? "+" : ""}
                {inr(res.delta_min_balance_inr)}
              </strong>
            </span>
          </div>

          <p
            className={`rounded-md px-3 py-2 text-xs font-medium ${
              res.new_stress_count > 0
                ? "bg-amber-50 text-amber-800"
                : "bg-emerald-50 text-emerald-800"
            }`}
          >
            {res.stress_message}
          </p>

          {res.updated_credit_recommendation.changed && (
            <p className="rounded-md bg-zinc-50 px-3 py-2 text-xs text-zinc-600">
              {res.updated_credit_recommendation.summary}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
