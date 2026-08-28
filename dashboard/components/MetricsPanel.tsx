"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getMetrics } from "@/lib/api";
import type { MetricsResponse } from "@/lib/types";

const REFRESH_MS = 30_000;
const PIE_COLORS = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0891b2"];

function inr(n: number) {
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

export function MetricsPanel({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<MetricsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const m = await getMetrics();
        if (alive) {
          setData(m);
          setErr(null);
          setUpdatedAt(new Date());
        }
      } catch (e: any) {
        if (alive) setErr(e.message);
      }
    };
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [refreshKey]);

  if (err) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        /metrics error: {err}
      </div>
    );
  }
  if (!data || !data.decisions_logged) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
        No decisions logged yet — adjust a profile to generate traffic.
      </div>
    );
  }

  const tierData = Object.entries(data.avg_wtp_by_segment?.by_city_tier ?? {}).map(
    ([k, v]) => ({ name: k.replace("tier_", "Tier "), wtp: Number(v.toFixed(3)) }),
  );
  const offerData = Object.entries(data.conversion_rate_by_offer_type ?? {}).map(
    ([k, v]) => ({ name: k, conv: Number((v * 100).toFixed(1)) }),
  );
  const ipData = Object.entries(data.traffic_quality?.ip_type_counts ?? {}).map(
    ([k, v]) => ({ name: k, value: v }),
  );
  const rev = data.revenue_lift_simulation;
  const revData = rev
    ? [
        { name: "Flat pricing", value: Math.round(rev.expected_revenue_flat_pricing) },
        { name: "WTP pricing", value: Math.round(rev.expected_revenue_wtp_pricing) },
      ]
    : [];
  const featData = (data.top_features_driving_wtp ?? []).map((f) => ({
    name: f.feature,
    v: Number(f.mean_abs_shap.toFixed(4)),
  }));

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-ink">
          Live metrics ({data.decisions_logged} decisions
          {data.db_backend ? ` · ${data.db_backend}` : ""})
        </p>
        <span className="text-[10px] text-slate-400">
          auto-refresh 30s
          {updatedAt ? ` · ${updatedAt.toLocaleTimeString()}` : ""}
        </span>
      </div>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        <Chart title="Avg WTP multiplier by city tier">
          <BarChart data={tierData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis domain={[0.85, 1.25]} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="wtp" fill="#2563eb" radius={[3, 3, 0, 0]} />
          </BarChart>
        </Chart>

        <Chart title="Conversion rate by offer type (%)">
          <BarChart data={offerData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 9 }} interval={0} angle={-15} height={40} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="conv" fill="#059669" radius={[3, 3, 0, 0]} />
          </BarChart>
        </Chart>

        <Chart title="Revenue: WTP pricing vs flat">
          <BarChart data={revData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => inr(v)} width={70} />
            <Tooltip formatter={(v: number) => inr(v)} />
            <Bar dataKey="value" radius={[3, 3, 0, 0]}>
              {revData.map((_, i) => (
                <Cell key={i} fill={i === 0 ? "#94a3b8" : "#2563eb"} />
              ))}
            </Bar>
          </BarChart>
        </Chart>

        <Chart title="Top features driving WTP (mean |SHAP|)">
          <BarChart data={featData} layout="vertical" margin={{ left: 20 }}>
            <XAxis type="number" tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} />
            <Tooltip />
            <Bar dataKey="v" fill="#7c3aed" radius={[0, 3, 3, 0]} />
          </BarChart>
        </Chart>

        <Chart title="Traffic mix by network type">
          <PieChart>
            <Pie
              data={ipData}
              dataKey="value"
              nameKey="name"
              outerRadius={70}
              label={(d) => d.name}
            >
              {ipData.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Legend wrapperStyle={{ fontSize: 10 }} />
          </PieChart>
        </Chart>

        {rev && (
          <div className="flex flex-col justify-center rounded-lg bg-slate-50 p-4">
            <p className="text-xs text-slate-500">Estimated gross-margin lift</p>
            <p
              className={`text-2xl font-bold ${
                rev.pct_lift >= 0 ? "text-brand-dark" : "text-amber-700"
              }`}
            >
              {rev.pct_lift >= 0 ? "+" : ""}
              {rev.pct_lift.toFixed(1)}%
            </p>
            <p className="text-xs text-slate-500">
              {inr(rev.margin_absolute_lift ?? rev.absolute_lift ?? 0)} extra
              margin across {data.decisions_logged} decisions vs charging list
              price to everyone
              {typeof rev.revenue_pct_lift === "number" && (
                <>
                  {" "}
                  · revenue {rev.revenue_pct_lift >= 0 ? "+" : ""}
                  {rev.revenue_pct_lift.toFixed(1)}%
                </>
              )}
              .
            </p>
            <p className="mt-2 text-[10px] text-slate-400">
              assumes {((rev.gross_margin_assumption ?? 0.45) * 100).toFixed(0)}%
              gross margin, COGS unchanged by price
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Chart({ title, children }: { title: string; children: any }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-slate-500">{title}</p>
      <ResponsiveContainer width="100%" height={180}>
        {children}
      </ResponsiveContainer>
    </div>
  );
}
