"use client";

import { useEffect, useState } from "react";
import type { PricingResponse } from "@/lib/types";
import { PRODUCT } from "@/lib/profiles";
import { ShapBars } from "./ShapBars";

const OFFER_COPY: Record<string, { label: string; tone: string }> = {
  extended_warranty: { label: "Free 1-year extended warranty", tone: "premium" },
  priority_support: { label: "Priority customer support", tone: "premium" },
  free_delivery: { label: "Free delivery", tone: "nudge" },
  cashback_5pct: { label: "5% cashback", tone: "nudge" },
  none: { label: "No additional offer", tone: "neutral" },
};

const PAY_LABEL: Record<string, string> = {
  UPI: "UPI",
  Credit_Card: "Credit Card",
  Debit_Card: "Debit Card",
  COD: "Cash on Delivery",
  Wallet: "Wallet",
};

function inr(n: number) {
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export function CheckoutPanel({
  title,
  subtitle,
  accent,
  result,
  loading,
  error,
}: {
  title: string;
  subtitle: string;
  accent: "emerald" | "amber";
  result: PricingResponse | null;
  loading: boolean;
  error: string | null;
}) {
  const [revealed, setRevealed] = useState(false);

  // replay the "personalising..." reveal whenever a fresh result lands
  useEffect(() => {
    if (loading) {
      setRevealed(false);
      return;
    }
    if (result) {
      const t = setTimeout(() => setRevealed(true), 550);
      return () => clearTimeout(t);
    }
  }, [loading, result]);

  const accentBar =
    accent === "emerald" ? "bg-emerald-500" : "bg-amber-500";
  const accentText =
    accent === "emerald" ? "text-emerald-700" : "text-amber-700";
  const accentSoft =
    accent === "emerald" ? "bg-emerald-50" : "bg-amber-50";

  const offer = result ? OFFER_COPY[result.offer_type] ?? OFFER_COPY.none : null;
  const showPersonalising = loading || !revealed;

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className={`${accentBar} h-1 w-full`} />
      <div className="border-b border-slate-100 px-5 py-3">
        <p className={`text-sm font-semibold ${accentText}`}>{title}</p>
        <p className="text-xs text-slate-500">{subtitle}</p>
      </div>

      {/* product row */}
      <div className="flex gap-4 px-5 py-4">
        <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-3xl">
          {"\u{1F45F}"}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{PRODUCT.name}</p>
          <p className="text-xs text-slate-500">
            {PRODUCT.brand} · Fashion · Sold by RunHub
          </p>
          <p className="mt-1 text-xs text-slate-400 line-through">
            MRP {inr(PRODUCT.list_price)}
          </p>
        </div>
      </div>

      {/* price / decision area */}
      <div className={`mx-5 mb-4 rounded-lg ${accentSoft} p-4`}>
        {error ? (
          <p className="text-sm text-red-600">API error: {error}</p>
        ) : showPersonalising ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <span className="h-2 w-2 animate-ping rounded-full bg-brand" />
              personalising checkout…
            </div>
            <div className="shimmer h-8 w-40 rounded bg-slate-200" />
            <div className="shimmer h-4 w-56 rounded bg-slate-200" />
          </div>
        ) : (
          result && (
            <div className="animate-pop-in space-y-3">
              <div className="flex items-end gap-3">
                <span className="text-3xl font-bold text-ink">
                  {inr(result.final_price)}
                </span>
                <span
                  className={`mb-1 rounded px-1.5 py-0.5 text-xs font-medium ${
                    result.price_delta_pct >= 0
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-amber-100 text-amber-700"
                  }`}
                >
                  {result.price_delta_pct >= 0 ? "+" : ""}
                  {result.price_delta_pct.toFixed(1)}% vs list
                </span>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {offer && offer.label !== OFFER_COPY.none.label && (
                  <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
                    {"\u{1F381}"} {offer.label}
                  </span>
                )}
                {result.instant_refund_eligible && (
                  <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200">
                    {"⚡"} Instant refund
                  </span>
                )}
                {result.cod_eligible && (
                  <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
                    COD available
                  </span>
                )}
                <span className="rounded-full bg-white px-2 py-0.5 text-xs text-slate-500 ring-1 ring-slate-200">
                  confidence: {result.confidence}
                </span>
              </div>

              {/* payment methods, personalised order */}
              <div>
                <p className="mb-1 text-xs font-medium text-slate-500">
                  Payment options (personalised order)
                </p>
                <div className="flex flex-col gap-1">
                  {result.payment_methods_shown.map((m, i) => (
                    <div
                      key={m}
                      className={`flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs ${
                        i === 0
                          ? "border-brand bg-brand/5 font-medium text-brand-dark"
                          : "border-slate-200 text-slate-600"
                      }`}
                    >
                      <span>{PAY_LABEL[m] ?? m}</span>
                      {i === 0 && <span className="text-[10px]">shown first</span>}
                    </div>
                  ))}
                </div>
              </div>

              <button className="w-full rounded-md bg-ink py-2 text-sm font-medium text-white">
                Pay {inr(result.final_price)}
              </button>

              <p className="text-[11px] leading-relaxed text-slate-500">
                {result.reasoning}
              </p>
              <p className="text-[10px] text-slate-400">
                decision in {result.latency_ms.toFixed(1)} ms / {result.budget_ms}{" "}
                ms budget
                {result.budget_exceeded ? " · OVER BUDGET" : ""}
                {" · WTP x"}
                {result.wtp_multiplier.toFixed(3)}
                {result.conversion_probability != null &&
                  ` · P(convert) ${(result.conversion_probability * 100).toFixed(0)}%`}
              </p>
            </div>
          )
        )}
      </div>

      {/* SHAP mini chart */}
      {result && !showPersonalising && (
        <div className="border-t border-slate-100 px-5 py-3">
          <ShapBars shap={result.shap_top} />
        </div>
      )}
    </div>
  );
}
