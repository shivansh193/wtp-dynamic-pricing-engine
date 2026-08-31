"use client";

import { useEffect, useMemo, useState } from "react";
import { completeSession, personalize } from "@/lib/api";
import { PAYMENT_LABEL, PRODUCT, inr, signalsFromConfig } from "@/lib/profiles";
import { useSessionsFeed } from "@/lib/ws";
import type { CheckoutConfig, PricingResponse, SessionConfig } from "@/lib/types";
import { PriceReveal } from "./PriceReveal";
import { WhyThisPrice } from "./WhyThisPrice";

const BADGE_LABEL: Record<string, string> = {
  easy_returns: "Easy 10-day returns",
  return_30d: "30-day no-questions returns",
  secure_checkout: "Secure checkout",
  verified_seller: "Verified seller",
  cod_available: "Cash on Delivery available",
  delivery_tracked: "Live order tracking",
  quality_checked: "Sealed & quality-checked",
};

// what each friction means for the shopper, in plain words
const FRICTION_COPY: Record<string, { what: string; doing: string }> = {
  price_sensitivity: {
    what: "you're weighing the price carefully",
    doing:
      "we're showing the monthly EMI and the effective price so the number is easy to say yes to",
  },
  trust_deficit: {
    what: "this might be your first order with this store",
    doing:
      "we're surfacing recent buyers, a matching review and the guarantees that matter here",
  },
  decision_paralysis: {
    what: "there's a lot to compare",
    doing: "we're leading with the one ranking that makes this an easy call",
  },
  payment_friction: {
    what: "your preferred way to pay isn't always the default",
    doing: "we've put it first and pre-opened it, and offered a split-payment option",
  },
  delivery_anxiety: {
    what: "delivery and returns are the usual worry on an order like this",
    doing: "we're giving you a firm delivery date and the returns policy up front",
  },
  urgency_insensitive: {
    what: "you know what you want",
    doing: "we're highlighting quality and warranty instead of a countdown",
  },
};

const INTERVENTION_LABEL: Record<string, string> = {
  emi_breakdown: "an EMI breakdown",
  price_anchor: "a market-price comparison",
  micro_commitment: "a pay-later option",
  social_proof_counter: "a live buyer count",
  dynamic_trust_badges: "store guarantees",
  relevant_review: "a review from a shopper like you",
  comparison_eliminator: "a category ranking",
  soft_urgency: "a low-stock note",
  price_lock: "a 24-hour price lock",
  payment_reorder: "your preferred payment method first",
  cod_bridge: "a split-payment option",
  one_tap_next_time: "one-tap checkout next time",
  delivery_promise: "a firm delivery date",
  return_guarantee_prominent: "the returns guarantee",
  packaging_promise: "a packaging guarantee",
  quality_signal: "the verified-buyer rating",
  premium_highlight: "the included warranty & support",
  exclusivity: "a returning-customer offer",
};

function CalendarIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-5 w-5 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  );
}

export function DynamicCheckout({
  result,
  sessionId,
  config,
  sessionCreatedAt,
  onResult,
}: {
  result: PricingResponse;
  sessionId: string;
  config: SessionConfig;
  sessionCreatedAt?: string;
  onResult?: (r: PricingResponse) => void;
}) {
  const cfg = result.checkout_config;
  // graceful fallback for a backend that predates checkout_config
  if (!cfg) {
    return (
      <PriceReveal
        result={result}
        sessionId={sessionId}
        config={config}
        onResult={onResult}
      />
    );
  }
  return (
    <Inner
      cfg={cfg}
      result={result}
      sessionId={sessionId}
      config={config}
      sessionCreatedAt={sessionCreatedAt}
      onResult={onResult}
    />
  );
}

function Inner({
  cfg,
  result,
  sessionId,
  config,
  sessionCreatedAt,
  onResult,
}: {
  cfg: CheckoutConfig;
  result: PricingResponse;
  sessionId: string;
  config: SessionConfig;
  sessionCreatedAt?: string;
  onResult?: (r: PricingResponse) => void;
}) {
  const [purchased, setPurchased] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [view, setView] = useState<"emi" | "full">(
    cfg.price_display === "emi" && cfg.emi_amount ? "emi" : "full",
  );
  const [expanded, setExpanded] = useState(0);
  const [codSplit, setCodSplit] = useState(false);
  const [whyPrice, setWhyPrice] = useState(false);
  const [whyOffer, setWhyOffer] = useState(false);

  // ---- session-time clock (urgency never shows on first load) ----
  const startedAt = useMemo(
    () => (sessionCreatedAt ? new Date(sessionCreatedAt).getTime() : Date.now()),
    [sessionCreatedAt],
  );
  const [elapsed, setElapsed] = useState(() =>
    Math.max(0, (Date.now() - startedAt) / 1000),
  );
  useEffect(() => {
    const id = setInterval(
      () => setElapsed(Math.max(0, (Date.now() - startedAt) / 1000)),
      1000,
    );
    return () => clearInterval(id);
  }, [startedAt]);
  const showUrgency =
    !!cfg.urgency_message && elapsed >= (cfg.urgency_min_seconds ?? 180);

  // ---- live social proof (websocket-nudged + slow tick) ----
  const [proof, setProof] = useState(cfg.social_proof_count ?? 0);
  useSessionsFeed([], {
    onEvent: () => cfg.social_proof_live && setProof((p) => p + 1),
  });
  useEffect(() => {
    if (!cfg.social_proof_live) return;
    const id = setInterval(
      () => setProof((p) => p + 1 + Math.floor(Math.random() * 2)),
      1000 * (6 + Math.random() * 4),
    );
    return () => clearInterval(id);
  }, [cfg.social_proof_live]);

  const markup = cfg.is_markup;
  const price = cfg.final_price;
  const saved = Math.max(0, cfg.list_price - price);
  const methods = cfg.payment_method_order.length
    ? cfg.payment_method_order
    : result.payment_methods_shown;
  const codUpfront = cfg.cod_split_offer
    ? Math.round((price * cfg.cod_split_offer.upfront_pct) / 100)
    : 0;

  const buy = async () => {
    try {
      await completeSession(sessionId);
    } catch {
      /* demo */
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
          {PRODUCT.name} · {inr(codSplit && codUpfront ? codUpfront : price)}
          {codSplit && codUpfront ? " now" : ""}
        </p>
        <p className="mt-1 text-xs text-emerald-600">
          This is a demo — no payment was taken.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg animate-pop-in space-y-3">
      {/* product */}
      <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-slate-100 text-2xl">
          {PRODUCT.emoji}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">{PRODUCT.name}</p>
          <p className="text-xs text-slate-500">{PRODUCT.brand}</p>
        </div>
        {cfg.offer_headline && (
          <span className="ml-auto rounded-full bg-brand/10 px-2.5 py-1 text-[11px] font-medium text-brand-dark">
            {cfg.offer_headline}
          </span>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        {/* ---- price ---- */}
        <PriceBlock
          cfg={cfg}
          view={view}
          markup={markup}
          saved={saved}
        />
        {cfg.emi_amount && (
          <div className="mt-2 inline-flex rounded-md border border-slate-200 p-0.5 text-[11px]">
            {(["emi", "full"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`rounded px-2 py-1 ${
                  view === v
                    ? "bg-ink text-white"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {v === "emi" ? `EMI / mo` : "Full price"}
              </button>
            ))}
          </div>
        )}

        {/* markup: what's included + net benefit */}
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
                About {inr(result.net_vs_standard_inr)} ahead versus the standard
                price.
              </p>
            )}
          </div>
        )}

        {/* ---- delivery promise ---- */}
        {cfg.delivery_promise && (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-emerald-800">
            <span className="text-emerald-600">
              <CalendarIcon />
            </span>
            <div>
              <p className="text-sm font-semibold">{cfg.delivery_promise}</p>
              <p className="text-[11px] text-emerald-600">
                Free delivery · order in the next few hours
              </p>
            </div>
          </div>
        )}

        {/* ---- urgency (only after N minutes of session time) ---- */}
        {showUrgency && (
          <p className="mt-3 animate-pulse rounded-md bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
            ⏳ {cfg.urgency_message}
          </p>
        )}

        {/* ---- social proof ---- */}
        {cfg.social_proof_live && proof > 0 && (
          <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-600">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            <span>
              <strong className="tabular-nums">{proof.toLocaleString()}</strong>{" "}
              people bought this in the last 24 hours
            </span>
          </p>
        )}

        {/* ---- review snippet ---- */}
        {cfg.review_snippet && (
          <p className="mt-3 border-l-2 border-slate-200 pl-3 text-xs italic text-slate-500">
            “{cfg.review_snippet}”
          </p>
        )}

        {/* ---- quality / premium / exclusivity notes ---- */}
        {(cfg.quality_signal || cfg.premium_note || cfg.exclusivity_note) && (
          <ul className="mt-3 space-y-1 text-xs text-slate-600">
            {cfg.quality_signal && <li>★ {cfg.quality_signal}</li>}
            {cfg.premium_note && <li>✔ {cfg.premium_note}</li>}
            {cfg.exclusivity_note && <li>✦ {cfg.exclusivity_note}</li>}
          </ul>
        )}

        {/* ---- trust badges ---- */}
        {cfg.trust_badges.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {cfg.trust_badges.slice(0, 3).map((b) => (
              <span
                key={b}
                className="rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700 ring-1 ring-slate-200"
              >
                {BADGE_LABEL[b] ?? b.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}

        {/* ---- payment methods (preferred pre-expanded) ---- */}
        <div className="mt-4">
          <p className="mb-1 text-xs font-medium text-slate-500">Pay with</p>
          <div className="flex flex-col gap-1">
            {methods.map((m, i) => (
              <div
                key={m}
                className={`rounded-md border text-xs ${
                  i === expanded
                    ? "border-brand bg-brand/5"
                    : "border-slate-200"
                }`}
              >
                <button
                  onClick={() => setExpanded(i)}
                  className="flex w-full items-center justify-between px-2.5 py-1.5"
                >
                  <span
                    className={
                      i === expanded
                        ? "font-medium text-brand-dark"
                        : "text-slate-600"
                    }
                  >
                    {PAYMENT_LABEL[m] ?? m}
                  </span>
                  {i === 0 && (
                    <span className="text-[10px] text-brand-dark">preferred</span>
                  )}
                </button>
                {i === expanded && (
                  <div className="border-t border-brand/20 px-2.5 py-2">
                    <PayStub method={m} />
                    {m === "COD" && cfg.cod_split_offer && (
                      <label className="mt-2 flex items-center gap-2 text-[11px] text-slate-600">
                        <input
                          type="checkbox"
                          checked={codSplit}
                          onChange={(e) => setCodSplit(e.target.checked)}
                          className="accent-brand"
                        />
                        Split it — pay {inr(codUpfront)} now (
                        {cfg.cod_split_offer.upfront_pct}%), the rest on delivery
                      </label>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <button
          onClick={buy}
          className="mt-4 w-full rounded-md bg-ink py-2.5 text-sm font-semibold text-white"
        >
          {codSplit && codUpfront
            ? `Pay ${inr(codUpfront)} now · rest on delivery`
            : "Complete Purchase"}
        </button>

        {markup && (
          <button
            onClick={useStandardPrice}
            disabled={switching}
            className="mt-2 w-full text-center text-xs text-slate-400 underline underline-offset-2 hover:text-slate-600 disabled:opacity-50"
          >
            {switching
              ? "updating…"
              : `Prefer the standard price? Continue at ${inr(cfg.list_price)}`}
          </button>
        )}
      </div>

      {/* ---- why this price? / why this offer? ---- */}
      <div className="rounded-xl border border-slate-200 bg-white text-xs">
        <Disclosure
          open={whyPrice}
          onClick={() => setWhyPrice((o) => !o)}
          label="Why this price?"
        >
          <FrictionExplainer cfg={cfg} markup={markup} saved={saved} />
        </Disclosure>
        <Disclosure
          open={whyOffer}
          onClick={() => setWhyOffer((o) => !o)}
          label="Why this offer?"
          border
        >
          <p className="text-slate-600">
            This checkout leads with{" "}
            <strong>
              {INTERVENTION_LABEL[cfg.primary_intervention] ??
                cfg.primary_intervention.replace(/_/g, " ")}
            </strong>
            . {cfg.psychological_mechanism}.
          </p>
          {result.offer_label && !markup && (
            <p className="mt-1 text-slate-500">
              You also get <strong>{result.offer_label}</strong> with this order.
            </p>
          )}
        </Disclosure>
      </div>

      {/* keep the SHAP-level detail available for the curious */}
      <WhyThisPrice
        shap={result.shap_top}
        markup={markup}
        offerLabel={result.offer_label}
        offerValue={result.offer_value_inr}
      />
    </div>
  );
}

function PriceBlock({
  cfg,
  view,
  markup,
  saved,
}: {
  cfg: CheckoutConfig;
  view: "emi" | "full";
  markup: boolean;
  saved: number;
}) {
  if (cfg.emi_amount && view === "emi") {
    return (
      <div>
        <div className="flex items-end gap-2">
          <span className="text-4xl font-bold text-ink">
            {inr(cfg.emi_amount)}
          </span>
          <span className="mb-1.5 text-sm text-slate-500">
            / mo × {cfg.emi_months}
          </span>
        </div>
        <p className="mt-0.5 text-xs text-slate-400">
          0% interest · {inr(cfg.final_price)} total
          {cfg.anchor_price && cfg.anchor_price > cfg.final_price && (
            <>
              {" · "}
              <span className="line-through">
                market ~{inr(cfg.anchor_price)}
              </span>
            </>
          )}
        </p>
      </div>
    );
  }
  return (
    <div>
      <div className="flex items-end gap-3">
        <span className="text-4xl font-bold text-ink">
          {inr(cfg.final_price)}
        </span>
        {!markup && saved > 0 && (
          <span className="mb-1.5 rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
            You save {inr(saved)}
          </span>
        )}
      </div>
      {cfg.price_display === "anchored" &&
      cfg.anchor_price &&
      cfg.anchor_price > cfg.final_price ? (
        <p className="mt-0.5 text-xs text-slate-400">
          <span className="line-through">
            market price ~{inr(cfg.anchor_price)}
          </span>
        </p>
      ) : (
        !markup &&
        saved > 0 && (
          <p className="mt-0.5 text-xs text-slate-400">
            <span className="line-through">MRP {inr(cfg.list_price)}</span>
          </p>
        )
      )}
    </div>
  );
}

function FrictionExplainer({
  cfg,
  markup,
  saved,
}: {
  cfg: CheckoutConfig;
  markup: boolean;
  saved: number;
}) {
  const copy = FRICTION_COPY[cfg.friction_type];
  const drivers = (cfg.friction_drivers ?? []).map((d) => d.signal).slice(0, 3);
  return (
    <div className="space-y-1.5 text-slate-600">
      <p>
        Your price is set from your shopping profile, inside a band the store
        controls — never more than a small step above list, and a price-sensitive
        shopper is never charged more than {inr(cfg.list_price)}.
      </p>
      {copy && (
        <p>
          We think {copy.what}
          {drivers.length > 0 && (
            <span className="text-slate-400"> ({drivers.join("; ")})</span>
          )}
          , so {copy.doing}.
        </p>
      )}
      {markup ? (
        <p>
          The small step up is matched with something of greater value included
          in the box — and you can switch to the standard price below.
        </p>
      ) : saved > 0 ? (
        <p>You&apos;re {inr(saved)} below MRP on this one.</p>
      ) : null}
    </div>
  );
}

function Disclosure({
  open,
  onClick,
  label,
  border,
  children,
}: {
  open: boolean;
  onClick: () => void;
  label: string;
  border?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={border ? "border-t border-slate-100" : ""}>
      <button
        onClick={onClick}
        className="flex w-full items-center justify-between px-4 py-2.5 font-medium text-slate-700"
      >
        {label}
        <span className="text-slate-300">{open ? "−" : "+"}</span>
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}

function PayStub({ method }: { method: string }) {
  if (method === "UPI")
    return (
      <input
        disabled
        placeholder="you@upi"
        className="w-full rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-400"
      />
    );
  if (method === "COD")
    return (
      <p className="text-[11px] text-slate-500">
        Pay in cash when the order arrives.
      </p>
    );
  if (method === "Wallet")
    return (
      <p className="text-[11px] text-slate-500">
        Redirects to your wallet to approve.
      </p>
    );
  return (
    <input
      disabled
      placeholder="Card number"
      className="w-full rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-400"
    />
  );
}
