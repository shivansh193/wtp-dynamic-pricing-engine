"use client";

import { useState } from "react";
import type { ShapFeature } from "@/lib/types";

const PLAIN: Record<string, string> = {
  device_type: "the device you're shopping on",
  city_tier: "your city",
  income_tier: "your area",
  payment_method_preference: "your preferred payment method",
  time_of_day: "the time of day",
  day_of_week: "the day of the week",
  referral_source: "how you reached this store",
  ip_type: "your network",
  product_category: "this product category",
  ip_trust_multiplier: "your network trust",
  historical_aov: "your typical order size",
  return_rate: "your return history",
  payment_success_rate: "your payment reliability",
  cod_completion_rate: "your cash-on-delivery track record",
  cross_merchant_trust_score: "your overall shopping trust score",
  num_merchants_transacted: "how many stores you've shopped at",
  account_age_days: "how long you've been shopping online",
  cart_value: "this cart's value",
  is_festival_period: "the festival season",
  festival_intensity: "how big the current festival is",
  digital_demand_index: "how busy online shopping is right now",
  month: "the time of year",
};

export function WhyThisPrice({ shap }: { shap: ShapFeature[] }) {
  const [open, setOpen] = useState(false);
  const top2 = shap.filter((s) => s.feature).slice(0, 2);

  return (
    <div className="rounded-lg border border-slate-200">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-slate-700"
      >
        Why this price?
        <span className="text-slate-400">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
          {top2.length === 0 && <p>Pricing is based on your overall profile.</p>}
          {top2.map((s, i) => {
            const up = s.shap >= 0;
            return (
              <p key={i}>
                <span className="font-medium text-slate-800">
                  {PLAIN[s.feature] ?? s.feature}
                </span>{" "}
                {up
                  ? "suggests a premium experience fits you, nudging the price up"
                  : "suggests you're price-sensitive here, bringing the price down"}
                .
              </p>
            );
          })}
          <p className="pt-1 text-xs text-slate-400">
            Your price is always within +15% / −10% of the list price. We never
            charge a price-sensitive shopper more than list.
          </p>
        </div>
      )}
    </div>
  );
}
