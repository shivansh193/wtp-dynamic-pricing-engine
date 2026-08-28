"use client";

import { useState } from "react";
import { completeSession, personalize } from "@/lib/api";
import { PAYMENT_LABEL, PRODUCT, inr, signalsFromConfig } from "@/lib/profiles";
import type { PricingResponse, SessionConfig } from "@/lib/types";
import { WhyThisPrice } from "./WhyThisPrice";

export function PriceReveal({
  result,
  sessionId,
  config,
  onResult,
}: {
  result: PricingResponse;
  sessionId: string;
  config: SessionConfig;
  onResult?: (r: PricingResponse) => void;
}) {
  const [purchased, setPurchased] = useState(false);
  const [switching, setSwitching] = useState(false);
  const markup = result.is_markup;
  const saved = Math.max(0, result.list_price - result.final_price);

  const buy = async () => {
    try {
      await completeSession(sessionId);
    } catch {
      /* demo - ignore */
    }
    setPurchased(true);
  };

  const useStandardPrice = async () => {
    setSwitching(true);
    try {
      const r = await personalize(
        signalsFromConfig(config, sessionId, { forceListPrice: true }),
      );
      onResult?.(r);
    } catch {
      /* keep current */
    } finally {
      setSwitching(false);
    }
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
      {/* product */}
      <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-slate-100 text-2xl">
          {PRODUCT.emoji}
        </div>
        <div>
          <p className="text-sm font-medium text-ink">{PRODUCT.name}</p>
          <p className="text-xs text-slate-500">{PRODUCT.brand}</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        {/* price */}
        <div className="flex items-end gap-3">
          <span className="text-4xl font-bold text-ink">
            {inr(result.final_price)}
          </span>
          {!markup && saved > 0 && (
            <span className="mb-1.5 rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
              You save {inr(saved)}
            </span>
          )}
        </div>
        {!markup && saved > 0 && (
          <p className="mt-0.5 text-xs text-slate-400">
            <span className="line-through">MRP {inr(result.list_price)}</span>
          </p>
        )}

        {/* markup: lead with what's included, and the net benefit */}
        {markup && result.offer_label && (
          <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-xs font-medium text-slate-500">
              Included with your order
            </p>
            <p className="mt-0.5 text-sm font-medium text-ink">
              🎁 {result.offer_label}
              {result.offer_value_inr > 0 && (
                <span className="font-normal text-slate-500">
                  {" "}
                  — worth about {inr(result.offer_value_inr)}
                </span>
              )}
            </p>
            {result.net_vs_standard_inr > 0 && (
              <p className="mt-1 text-xs font-medium text-emerald-700">
                You come out about {inr(result.net_vs_standard_inr)} ahead versus
                the standard price.
              </p>
            )}
          </div>
        )}

        {/* eligibility badges */}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {!markup && result.offer_type !== "none" && result.offer_label && (
            <Badge>🎁 {result.offer_label}</Badge>
          )}
          {result.instant_refund_eligible && (
            <Badge tone="emerald">⚡ Instant refund</Badge>
          )}
          {result.cod_eligible && <Badge>Cash on Delivery available</Badge>}
        </div>

        {/* payment options */}
        <div className="mt-4">
          <p className="mb-1 text-xs font-medium text-slate-500">Payment options</p>
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

        {/* the visible escape hatch on a markup */}
        {markup && (
          <button
            onClick={useStandardPrice}
            disabled={switching}
            className="mt-2 w-full text-center text-xs text-slate-400 underline underline-offset-2 hover:text-slate-600 disabled:opacity-50"
          >
            {switching
              ? "updating…"
              : `Prefer the standard price? Continue at ${inr(result.list_price)}`}
          </button>
        )}
      </div>

      <WhyThisPrice
        shap={result.shap_top}
        markup={markup}
        offerLabel={result.offer_label}
        offerValue={result.offer_value_inr}
      />
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
