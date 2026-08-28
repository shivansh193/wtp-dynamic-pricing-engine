"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const LABELS: Record<string, string> = {
  device_type: "Device type",
  city_tier: "City tier",
  income_tier: "Income tier",
  payment_method_preference: "Payment pref",
  time_of_day: "Time of day",
  day_of_week: "Day of week",
  referral_source: "Referral",
  ip_type: "Network type",
  product_category: "Category",
  ip_trust_multiplier: "IP trust",
  historical_aov: "Hist. AOV",
  return_rate: "Return rate",
  payment_success_rate: "Pay success",
  cod_completion_rate: "COD completion",
  cross_merchant_trust_score: "Trust score",
  num_merchants_transacted: "# merchants",
  account_age_days: "Account age",
  cart_value: "Cart value",
  is_festival_period: "Festival",
  festival_intensity: "Festival intensity",
  digital_demand_index: "Digital demand",
  month: "Month",
};

type ShapItem = { feature: string; value: string | number; shap: number };

/**
 * A left-to-right SHAP waterfall: start at the base value, add each feature's
 * contribution in decreasing-magnitude order, land on the predicted WTP.
 */
export function ShapWaterfall({
  baseValue,
  contributions,
  predicted,
  maxRows = 10,
}: {
  baseValue: number;
  contributions: ShapItem[];
  predicted?: number;
  maxRows?: number;
}) {
  const sorted = [...contributions]
    .filter((c) => c.feature)
    .sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap));
  const shown = sorted.slice(0, maxRows);
  const restSum = sorted.slice(maxRows).reduce((s, c) => s + c.shap, 0);
  // SHAP is additive: base + sum(all contributions) = the model's raw output.
  const shapTotal = baseValue + sorted.reduce((s, c) => s + c.shap, 0);
  // the price actually shown may be the raw output clipped to the +15%/-10% band
  const capped = predicted != null && Math.abs(predicted - shapTotal) > 0.003;

  const rows: { name: string; sub: string; start: number; delta: number }[] = [];
  let running = baseValue;
  rows.push({ name: "Base (avg WTP)", sub: "", start: 0, delta: baseValue });
  for (const c of shown) {
    rows.push({
      name: LABELS[c.feature] ?? c.feature,
      sub: `= ${c.value}`,
      start: running,
      delta: c.shap,
    });
    running += c.shap;
  }
  if (Math.abs(restSum) > 1e-4) {
    rows.push({ name: `+${sorted.length - maxRows} others`, sub: "", start: running, delta: restSum });
    running += restSum;
  }
  rows.push({
    name: capped ? "Model output (pre-cap)" : "Predicted WTP",
    sub: `×${shapTotal.toFixed(3)}`,
    start: 0,
    delta: shapTotal,
  });

  // stacked bar: [invisible offset, visible delta]
  const TOTAL_ROWS = new Set(["Base (avg WTP)", "Predicted WTP", "Model output (pre-cap)"]);
  const data = rows.map((r) => {
    const isTotal = TOTAL_ROWS.has(r.name);
    const lo = isTotal ? 0 : Math.min(r.start, r.start + r.delta);
    const mag = isTotal ? Math.abs(r.delta) : Math.abs(r.delta);
    return {
      name: r.name,
      sub: r.sub,
      offset: lo,
      mag,
      delta: r.delta,
      isTotal,
      up: r.delta >= 0,
    };
  });

  const domainMax = Math.max(...data.map((d) => d.offset + d.mag), 1.3) * 1.02;
  const domainMin = Math.min(...data.map((d) => d.offset), 0.8) * 0.99;

  return (
    <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 34)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 60, top: 4, bottom: 4 }}>
        <XAxis type="number" domain={[domainMin, domainMax]} tick={{ fontSize: 10 }} />
        <YAxis
          type="category"
          dataKey="name"
          width={130}
          tick={{ fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          formatter={(_v, _n, p: any) =>
            p.payload.isTotal
              ? `×${p.payload.delta.toFixed(3)}`
              : `${p.payload.delta >= 0 ? "+" : ""}${p.payload.delta.toFixed(3)}  ${p.payload.sub}`
          }
          labelFormatter={(l) => l}
        />
        <Bar dataKey="offset" stackId="w" fill="transparent" />
        <Bar dataKey="mag" stackId="w" radius={[2, 2, 2, 2]}>
          {data.map((d, i) => (
            <Cell
              key={i}
              fill={d.isTotal ? "#0f172a" : d.up ? "#2563eb" : "#dc2626"}
            />
          ))}
          <LabelList
            dataKey="delta"
            position="right"
            formatter={(v: number) => (v >= 0 ? `+${v.toFixed(3)}` : v.toFixed(3))}
            style={{ fontSize: 10, fill: "#475569" }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ShapWaterfallNote({
  baseValue,
  contributions,
  predicted,
}: {
  baseValue: number;
  contributions: { shap: number }[];
  predicted?: number;
}) {
  const shapTotal = baseValue + contributions.reduce((s, c) => s + c.shap, 0);
  if (predicted == null || Math.abs(predicted - shapTotal) <= 0.003) return null;
  return (
    <p className="mt-1 text-[10px] text-slate-400">
      SHAP sums to the model&apos;s raw output ×{shapTotal.toFixed(3)}; the price
      shown uses ×{predicted.toFixed(3)} after the +15% / −10% cap.
    </p>
  );
}
