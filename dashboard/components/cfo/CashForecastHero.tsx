"use client";

import {
  Area,
  ComposedChart,
  CartesianGrid,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { OracleForecast } from "@/lib/cfoTypes";
import { inr, shortDate } from "@/lib/cfoApi";

const FEST_EMOJI: Record<string, string> = {
  Diwali: "🪔",
  Holi: "🎨",
  Eid: "🌙",
  Christmas: "🎄",
  "FY-end": "📅",
};

export function CashForecastHero({ f }: { f: OracleForecast }) {
  const yhatByDate = new Map(f.forecast_curve.map((p) => [p.date, p]));
  const data = f.cash_position_curve.map((p) => {
    const dq = yhatByDate.get(p.date);
    return {
      date: p.date,
      hist: p.is_forecast ? null : p.balance,
      fc: p.is_forecast ? p.balance : null,
      fcLower: p.is_forecast ? p.lower : null,
      fcBand: p.is_forecast ? Math.max(0, p.upper - p.lower) : null,
      regime: p.regime,
      settlement: dq ? dq.yhat : null,
      sLower: dq ? dq.lower : null,
      sUpper: dq ? dq.upper : null,
    };
  });
  // stitch the line: last historical point also seeds the forecast line
  const lastHist = [...data].reverse().find((d) => d.hist != null);
  if (lastHist) lastHist.fc = lastHist.hist;

  const th = f.operating_threshold;
  const trendUp = f.current_cash_trend_pct >= 0;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-800">
          Settlement cash position — next 60 days
        </h2>
        <span className="text-[11px] text-zinc-400">
          engine: {f.engine} · generated {shortDate(f.generated_on)}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10 }}
            tickFormatter={shortDate}
            minTickGap={28}
          />
          <YAxis
            tick={{ fontSize: 10 }}
            width={54}
            tickFormatter={(v) => inr(v).replace("₹", "")}
          />
          <Tooltip content={<CashTooltip threshold={th} />} />

          {/* stress period shading */}
          {f.cash_stress_periods.map((s, i) => (
            <ReferenceArea
              key={i}
              x1={s.start}
              x2={s.end}
              fill="#ef4444"
              fillOpacity={0.08}
            />
          ))}

          {/* confidence band (forecast only) */}
          <Area
            type="monotone"
            dataKey="fcLower"
            stackId="ci"
            stroke="none"
            fill="none"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="fcBand"
            stackId="ci"
            stroke="none"
            fill="#6366f1"
            fillOpacity={0.12}
            isAnimationActive={false}
          />

          {/* operating threshold */}
          <ReferenceLine
            y={th}
            stroke="#dc2626"
            strokeDasharray="5 4"
            label={{
              value: `operating floor ${inr(th)}`,
              position: "insideBottomRight",
              fontSize: 10,
              fill: "#dc2626",
            }}
          />

          {/* festival markers */}
          {f.festival_markers.map((m) => (
            <ReferenceLine
              key={m.date}
              x={nearestDate(data, m.date)}
              stroke="#a1a1aa"
              strokeDasharray="2 3"
              label={{
                value: `${FEST_EMOJI[m.name] ?? "•"} ${m.name}`,
                position: "top",
                fontSize: 9,
                fill: "#71717a",
              }}
            />
          ))}

          <Line
            type="monotone"
            dataKey="hist"
            stroke="#18181b"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            name="actual"
          />
          <Line
            type="monotone"
            dataKey="fc"
            stroke="#4f46e5"
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={false}
            isAnimationActive={false}
            name="forecast"
          />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Stat
          label="Current cash position"
          value={inr(f.cash_on_hand)}
          sub={
            <span className={trendUp ? "text-emerald-600" : "text-amber-700"}>
              {trendUp ? "▲" : "▼"} {Math.abs(f.current_cash_trend_pct).toFixed(1)}% vs last week
            </span>
          }
        />
        <Stat
          label="Next stress period"
          value={
            f.next_stress_days == null
              ? "None in 60 days"
              : `${f.next_stress_days} days`
          }
          valueClass={f.next_stress_days == null ? "text-emerald-600" : "text-amber-700"}
          sub={
            f.cash_stress_periods[0]
              ? `${shortDate(f.cash_stress_periods[0].start)}–${shortDate(
                  f.cash_stress_periods[0].end,
                )} · trough ${inr(f.cash_stress_periods[0].trough_balance)}`
              : "forecast stays above the operating floor"
          }
        />
        <Stat
          label="Forecast accuracy (last 30d)"
          value={f.forecast_accuracy_mape == null ? "—" : `${(100 - f.forecast_accuracy_mape).toFixed(0)}%`}
          sub={
            f.forecast_accuracy_mape == null
              ? "insufficient history"
              : `MAPE ${f.forecast_accuracy_mape.toFixed(1)}% on held-out days`
          }
        />
      </div>
    </section>
  );
}

function Stat({
  label,
  value,
  sub,
  valueClass = "text-zinc-900",
}: {
  label: string;
  value: string;
  sub: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="rounded-lg bg-zinc-50 p-3">
      <p className="text-[10px] uppercase tracking-wide text-zinc-400">{label}</p>
      <p className={`mt-0.5 text-xl font-bold tabular-nums ${valueClass}`}>{value}</p>
      <p className="mt-0.5 text-[11px] text-zinc-500">{sub}</p>
    </div>
  );
}

function CashTooltip({ active, payload, label, threshold }: any) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const bal = row.fc ?? row.hist;
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-2 text-[11px] shadow-sm">
      <p className="font-semibold text-zinc-700">{shortDate(label)}</p>
      <p>
        Cash position: <strong>{inr(bal)}</strong>
      </p>
      {row.settlement != null && (
        <>
          <p className="text-zinc-500">
            Predicted settlement: {inr(row.settlement)}/day
          </p>
          <p className="text-zinc-400">
            CI {inr(row.sLower)} – {inr(row.sUpper)}
          </p>
        </>
      )}
      <p className="text-zinc-400">regime: {row.regime}</p>
      {bal != null && bal < threshold && (
        <p className="font-medium text-red-600">below operating floor</p>
      )}
    </div>
  );
}

function nearestDate(data: { date: string }[], target: string): string {
  const t = new Date(target).getTime();
  let best = data[0]?.date ?? target;
  let bestGap = Infinity;
  for (const d of data) {
    const g = Math.abs(new Date(d.date).getTime() - t);
    if (g < bestGap) {
      bestGap = g;
      best = d.date;
    }
  }
  return best;
}
