"use client";

import { useState } from "react";
import { inr } from "@/lib/profiles";
import type { ShapFeature } from "@/lib/types";

const PLAIN: Record<string, string> = {
  device_type: "the device you're shopping on",
  city_tier: "your city",
  income_tier: "your area",
  payment_method_preference: "how you usually pay",
  time_of_day: "the time of day",
  day_of_week: "the day of the week",
  referral_source: "how you reached this store",
  ip_type: "your network",
  product_category: "this product category",
  ip_trust_multiplier: "your network",
  historical_aov: "your typical order size",
  return_rate: "your return history",
  payment_success_rate: "your payment history",
  cod_completion_rate: "your delivery-acceptance history",
  cross_merchant_trust_score: "your overall shopping history",
  num_merchants_transacted: "how many stores you've shopped at",
  account_age_days: "how long you've shopped online",
  cart_value: "this cart's value",
  is_festival_period: "the festival season",
  festival_intensity: "the festival season",
  digital_demand_index: "how busy online shopping is right now",
  month: "the time of year",
};

export function WhyThisPrice({
  shap,
  markup,
  offerLabel,
  offerValue,
}: {
  shap: ShapFeature[];
  markup: boolean;
  offerLabel?: string;
  offerValue?: number;
}) {
  const [open, setOpen] = useState(false);
  const top2 = shap.filter((s) => s.feature).slice(0, 2);

  return (
    <div className="rounded-lg border border-slate-200">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-slate-700"
      >
        {markup ? "About this price" : "Why this price?"}
        <span className="text-slate-400">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
          {markup ? (
            <>
              <p>
                Your checkout is tailored to your shopping history — it includes{" "}
                {offerLabel ? (
                  <span className="font-medium text-slate-800">
                    {offerLabel.toLowerCase()}
                    {offerValue ? ` (worth about ${inr(offerValue)})` : ""}
                  </span>
                ) : (
                  "extras"
                )}{" "}
                that most shoppers don&apos;t get.
              </p>
              <p>
                {top2.length > 0 &&
                  `Signals like ${top2
                    .map((s) => PLAIN[s.feature] ?? s.feature)
                    .join(" and ")} suggest this bundle fits you. `}
                You can switch to the plain standard price at any time with the
                link above.
              </p>
            </>
          ) : (
            <>
              {top2.length === 0 && <p>Pricing is based on your overall profile.</p>}
              {top2.map((s, i) => (
                <p key={i}>
                  <span className="font-medium text-slate-800">
                    {PLAIN[s.feature] ?? s.feature}
                  </span>{" "}
                  {s.shap < 0
                    ? "suggests a better price fits you here."
                    : "was taken into account."}
                </p>
              ))}
              <p className="pt-1 text-xs text-slate-400">
                We never charge a price-sensitive shopper more than the list
                price.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
