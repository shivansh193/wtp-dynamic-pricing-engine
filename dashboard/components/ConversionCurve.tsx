"use client";

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

export function ConversionCurve({
  curve,
  chosenMultiplier,
  height = 200,
}: {
  curve: { price_multiplier: number; conversion_probability: number }[];
  chosenMultiplier?: number;
  height?: number;
}) {
  const data = curve.map((p) => ({
    x: p.price_multiplier,
    pct: Number((p.conversion_probability * 100).toFixed(1)),
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="x"
          tick={{ fontSize: 11 }}
          tickFormatter={(v) => `×${v}`}
          label={{ value: "price multiplier", position: "insideBottom", offset: -2, fontSize: 10 }}
        />
        <YAxis
          tick={{ fontSize: 11 }}
          domain={[0, 100]}
          tickFormatter={(v) => `${v}%`}
          width={40}
        />
        <Tooltip formatter={(v: number) => `${v}%`} labelFormatter={(l) => `×${l}`} />
        {chosenMultiplier != null && (
          <ReferenceLine
            x={Number(chosenMultiplier.toFixed(2))}
            stroke="#2563eb"
            strokeDasharray="4 2"
            label={{ value: "shown", fontSize: 10, fill: "#2563eb" }}
          />
        )}
        <Line
          type="monotone"
          dataKey="pct"
          stroke="#059669"
          strokeWidth={2}
          dot={{ r: 3 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
