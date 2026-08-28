"use client";

import { useState } from "react";
import { completeSession } from "@/lib/api";
import { OFFER_LABEL, PAYMENT_LABEL, PRODUCT, inr } from "@/lib/profiles";
import type { PricingResponse } from "@/lib/types";
import { WhyThisPrice } from "./WhyThisPrice";

export function PriceReveal({
  result,
  sessionId,
}: {
  result: PricingResponse;
  sessionId: string;
}) {
  const [purchased, setPurchased] = useState(false);
  const saved = result.list_price - result.final_price;
  const premium = result.price_delta_pct > 0;

  const buy = async () => {
    try {
      await completeSession(sessionId);
    } catch {
      /* ignore - dummy purchase */
    }
    setPurchased(true);
  };

  if (purchased) {
    return (
      <div className="mx-auto max-w-lg animate-pop-in rounded-xl border border-emerald-200 bg-emerald-50 p-8 text-center">
        <div className="text-4xl">✅</div>
        <p className="mt-2 text-lg font-semibold text-emerald-800">Order placed</p>
        <p className="text-sm text-emerald-700">
          {PRODUCT.name} · {inr(result.final_price)}
        </p>
        <p className="mt-1 text-xs text-emerald-600">
          This is a demo — no payment was taken.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg animate-pop-in space-y-4">
      <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-slate-100 text-2xl">
          {PRODUCT.emoji}
        </div>
        <div>
          <p className="text-sm font-medium text-ink">{PRODUCT.name}</p>
          <p className="text-xs text-slate-500">{PRODUCT.brand}</p>
          <p className="text-xs text-slate-400 line-through">
            MRP {inr(result.list_price)}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex items-end gap-3">
          <span className="text-4xl font-bold text-ink">
            {inr(result.final_price)}
          </span>
          <span
            className={`mb-1.5 rounded px-2 py-0.5 text-xs font-medium ${
              premium
                ? "bg-slate-100 text-slate-600"
                : "bg-emerald-100 text-emerald-700"
            }`}
          >
            {premium
              ? "Premium experience pricing"
              : `You saved ${inr(saved)}`}
          </span>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {result.offer_type !== "none" && (
            <Badge>🎁 {OFFER_LABEL[result.offer_type] ?? result.offer_type}</Badge>
          )}
          {result.instant_refund_eligible && (
            <Badge tone="emerald">⚡ Instant refund</Badge>
          )}
          {result.cod_eligible && <Badge>Cash on Delivery available</Badge>}
        </div>

        <div className="mt-4">
          <p className="mb-1 text-xs font-medium text-slate-500">
            Payment options
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
                <span>{PAYMENT_LABEL[m] ?? m}</span>
                {i === 0 && <span className="text-[10px]">recommended</span>}
              </div>
            ))}
          </div>
        </div>

        <button
          onClick={buy}
          className="mt-4 w-full rounded-md bg-ink py-2.5 text-sm font-semibold text-white"
        >
          Complete Purchase
        </button>
      </div>

      <WhyThisPrice shap={result.shap_top} />

      <p className="text-center text-[10px] text-slate-400">
        decision in {result.latency_ms.toFixed(0)} ms · WTP ×
        {result.wtp_multiplier.toFixed(3)} · confidence {result.confidence}
      </p>
    </div>
  );
}

function Badge({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone?: "emerald";
}) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${
        tone === "emerald"
          ? "bg-white text-emerald-700 ring-emerald-200"
          : "bg-white text-slate-700 ring-slate-200"
      }`}
    >
      {children}
    </span>
  );
}
