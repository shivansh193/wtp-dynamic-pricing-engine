"use client";

import { PAYMENT_LABEL } from "@/lib/profiles";

const METHODS = ["UPI", "Credit_Card", "Debit_Card", "COD", "Wallet"] as const;

export type Split = Record<string, number>; // fractions, sum ~1

/** How the shopper's payments break down. The mix (not just the favourite)
 *  feeds the trust score and COD reliability. */
export function PaymentSplitEditor({
  value,
  onChange,
  compact,
}: {
  value: Split;
  onChange: (s: Split) => void;
  compact?: boolean;
}) {
  const pct = (m: string) => Math.round((value[m] ?? 0) * 100);
  const total = METHODS.reduce((s, m) => s + (value[m] ?? 0), 0);

  const setOne = (m: string, p: number) => {
    onChange({ ...value, [m]: Math.max(0, p / 100) });
  };

  return (
    <div className={compact ? "space-y-1.5" : "space-y-2"}>
      {METHODS.map((m) => (
        <div key={m} className="flex items-center gap-2">
          <span className="w-24 shrink-0 text-[11px] text-slate-500">
            {PAYMENT_LABEL[m] ?? m}
          </span>
          <input
            type="range"
            min={0}
            max={100}
            value={pct(m)}
            onChange={(e) => setOne(m, Number(e.target.value))}
            className="flex-1 accent-brand"
          />
          <span className="w-9 shrink-0 text-right text-[11px] tabular-nums text-slate-600">
            {pct(m)}%
          </span>
        </div>
      ))}
      <p className="text-[10px] text-slate-400">
        {Math.abs(total - 1) < 0.02
          ? "adds up to 100%"
          : `adds up to ${Math.round(total * 100)}% — will be scaled to 100%`}
      </p>
    </div>
  );
}

export function evenSplit(): Split {
  return { UPI: 0.4, Credit_Card: 0.25, Debit_Card: 0.15, COD: 0.1, Wallet: 0.1 };
}
