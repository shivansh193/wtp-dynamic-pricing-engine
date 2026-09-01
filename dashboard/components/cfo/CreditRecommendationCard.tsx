"use client";

import { useEffect, useState } from "react";
import { getOracleLLMRecommendation, inr, shortDate } from "@/lib/cfoApi";
import type { LLMRecommendation, OracleForecast } from "@/lib/cfoTypes";
import { Skeleton } from "./Skeleton";

export function CreditRecommendationCard({ f }: { f: OracleForecast }) {
  const [rec, setRec] = useState<LLMRecommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [modal, setModal] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setFailed(false);
    setRec(null);
    getOracleLLMRecommendation({
      merchant_id: f.merchant_id,
      forecast: f,
      regime: f.regime,
      regime_confidence: f.regime_confidence,
      peer_comparison: f.peer_comparison,
      anomaly_flag: f.anomaly_flag,
      anomaly_explanation: f.anomaly_explanation,
      carry_cost_analysis: f.carry_cost_analysis,
      credit_apply_by_date: f.credit_apply_by_date,
    })
      .then((r) => {
        if (!alive) return;
        setRec(r);
      })
      .catch(() => alive && setFailed(true))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [f]);

  const cc = f.carry_cost_analysis;
  const stress = f.cash_stress_periods[0];

  return (
    <section className="rounded-lg border-2 border-brand/30 bg-white p-5">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-800">
          CFO recommendation
        </h2>
        {rec && (
          <span className="text-[10px] text-zinc-400">
            {rec.source === "llm" ? `${rec.model}` : "pattern-based"}
            {rec.cached ? " · cached" : ""}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-[92%]" />
          <Skeleton className="h-4 w-[85%]" />
        </div>
      ) : (
        <>
          <p className="text-[15px] leading-relaxed text-zinc-800">
            {rec?.recommendation}
          </p>
          {failed && (
            <p className="mt-1 text-[10px] text-amber-600">
              AI recommendation unavailable — showing pattern-based recommendation.
            </p>
          )}
        </>
      )}

      {/* credit timing optimiser */}
      <div className="mt-4 rounded-lg bg-zinc-50 p-3 text-xs">
        {stress && f.credit_apply_by_date ? (
          <>
            <p className="text-zinc-700">
              Apply by{" "}
              <strong className="text-brand-dark">
                {shortDate(f.credit_apply_by_date)}
              </strong>{" "}
              for funds to arrive before the stress trough on{" "}
              <strong>{shortDate(stress.trough_date)}</strong>.
            </p>
            <div className="mt-2 grid grid-cols-3 gap-2 tabular-nums">
              <KV k="Carry cost" v={inr(cc.carry_cost_inr)} />
              <KV k="Penalty avoided" v={inr(cc.late_payment_penalty_avoided_inr)} />
              <KV
                k="Net benefit"
                v={inr(cc.net_benefit_inr)}
                tone={cc.net_benefit_inr >= 0 ? "good" : "bad"}
              />
            </div>
          </>
        ) : (
          <p className="text-zinc-600">
            No borrowing needed — the forecast stays above your operating floor
            for the next 60 days.
          </p>
        )}
      </div>

      <button
        onClick={() => setModal(true)}
        disabled={!stress}
        className="mt-3 w-full rounded-md bg-brand py-2 text-xs font-semibold text-white hover:bg-brand-dark disabled:opacity-40"
      >
        Apply for Razorpay Capital
      </button>

      {modal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
          onClick={() => setModal(false)}
        >
          <div
            className="max-w-sm rounded-xl bg-white p-6 text-center shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-3xl">✅</div>
            <p className="mt-2 text-sm font-semibold text-zinc-800">
              Application submitted
            </p>
            <p className="mt-1 text-xs text-zinc-500">
              {stress
                ? `We'll disburse ${inr(cc.shortfall_inr)} to your settlement account so it lands before ${shortDate(
                    stress.trough_date,
                  )}. This is a demo — no real application was filed.`
                : "This is a demo — no real application was filed."}
            </p>
            <button
              onClick={() => setModal(false)}
              className="mt-4 rounded-md bg-zinc-900 px-4 py-1.5 text-xs font-medium text-white"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function KV({
  k,
  v,
  tone,
}: {
  k: string;
  v: string;
  tone?: "good" | "bad";
}) {
  return (
    <div className="rounded bg-white p-2">
      <p className="text-[9px] uppercase tracking-wide text-zinc-400">{k}</p>
      <p
        className={`font-semibold ${
          tone === "good"
            ? "text-emerald-600"
            : tone === "bad"
              ? "text-amber-700"
              : "text-zinc-800"
        }`}
      >
        {v}
      </p>
    </div>
  );
}
