"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import type { ShapFeature } from "@/lib/types";

const FEATURE_LABELS: Record<string, string> = {
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

export function ShapBars({ shap }: { shap: ShapFeature[] }) {
  const data = shap.slice(0, 3).map((s) => ({
    name: FEATURE_LABELS[s.feature] ?? s.feature,
    raw: `${s.feature} = ${s.value}`,
    shap: Number(s.shap.toFixed(4)),
  }));

  if (data.length === 0) {
    return (
      <p className="text-xs text-slate-400">No SHAP attribution available.</p>
    );
  }

  const maxAbs = Math.max(...data.map((d) => Math.abs(d.shap)), 0.01);

  return (
    <div>
      <p className="mb-1 text-xs font-medium text-slate-500">
        Top 3 drivers of this price (SHAP contribution to WTP)
      </p>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ left: 8, right: 40, top: 4, bottom: 4 }}
        >
          <XAxis
            type="number"
            domain={[-maxAbs * 1.1, maxAbs * 1.1]}
            hide
          />
          <YAxis
            type="category"
            dataKey="name"
            width={90}
            tick={{ fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Bar dataKey="shap" radius={[3, 3, 3, 3]} barSize={16}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.shap >= 0 ? "#2563eb" : "#dc2626"} />
            ))}
            <LabelList
              dataKey="shap"
              position="right"
              formatter={(v: number) => (v >= 0 ? `+${v}` : `${v}`)}
              style={{ fontSize: 10, fill: "#475569" }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-1 space-y-0.5">
        {data.map((d, i) => (
          <p key={i} className="text-[10px] text-slate-400">
            {d.raw}
          </p>
        ))}
      </div>
    </div>
  );
}
