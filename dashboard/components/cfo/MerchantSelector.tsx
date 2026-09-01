"use client";

import type { OracleMerchant } from "@/lib/cfoTypes";
import { inr } from "@/lib/cfoApi";

const CAT_COLOR: Record<string, string> = {
  fashion: "bg-pink-100 text-pink-700",
  electronics: "bg-indigo-100 text-indigo-700",
  grocery: "bg-emerald-100 text-emerald-700",
  home: "bg-amber-100 text-amber-700",
  services: "bg-sky-100 text-sky-700",
};

export function MerchantSelector({
  merchants,
  selected,
  onSelect,
}: {
  merchants: OracleMerchant[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const cur = merchants.find((m) => m.merchant_id === selected);
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-200 bg-white p-4">
      <select
        value={selected}
        onChange={(e) => onSelect(e.target.value)}
        className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium"
      >
        {merchants.map((m) => (
          <option key={m.merchant_id} value={m.merchant_id}>
            {m.name} — {m.category} · T{m.city_tier}
          </option>
        ))}
      </select>
      {cur && (
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`rounded-full px-2 py-0.5 font-medium capitalize ${
              CAT_COLOR[cur.category] ?? "bg-zinc-100 text-zinc-600"
            }`}
          >
            {cur.category}
          </span>
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 font-medium text-zinc-600">
            Tier {cur.city_tier}
          </span>
          <span className="text-zinc-400">
            ~{inr(cur.current_cash_position)} monthly settlement · safe floor{" "}
            {inr(cur.operating_threshold)}
          </span>
        </div>
      )}
    </div>
  );
}
