"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ConversionCurve } from "@/components/ConversionCurve";
import { ShapWaterfall } from "@/components/ShapWaterfall";
import { getDecision, getSegmentStats, getSession } from "@/lib/api";
import { DEVICE_LABEL, OFFER_LABEL, inr } from "@/lib/profiles";
import type { SegmentStats, SessionInfo } from "@/lib/types";

function trustBand(score?: number): string {
  if (score == null) return "unknown";
  if (score >= 80) return "80–100 (high)";
  if (score >= 60) return "60–80 (good)";
  if (score >= 40) return "40–60 (medium)";
  if (score >= 20) return "20–40 (low)";
  return "0–20 (very low)";
}

export default function MerchantPage({
  params,
}: {
  params: { session_id: string };
}) {
  const sid = params.session_id;
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [decision, setDecision] = useState<any | null>(null);
  const [seg, setSeg] = useState<SegmentStats | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getSession(sid)
      .then((s) => {
        setSession(s);
        if (s.segment_key) {
          getSegmentStats(s.segment_key).then(setSeg).catch(() => {});
        }
        if (s.status === "priced" || s.status === "converted") {
          getDecision(sid)
            .then((d) => setDecision(d.decisions?.[d.decisions.length - 1] ?? null))
            .catch(() => {});
        }
      })
      .catch((e) => setErr(e.message));
  }, [sid]);

  if (err) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        {err}
      </div>
    );
  }
  if (!session) {
    return <p className="text-sm text-slate-400">loading session…</p>;
  }

  const cfg = session.config;
  const res = session.result;
  const shapAll: { feature: string; value: any; shap: number }[] =
    decision?.shap_values?.all ?? res?.shap_top ?? [];
  const baseValue: number = decision?.shap_values?.base_value ?? 1.0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-base font-semibold text-ink">Merchant session view</h1>
          <p className="font-mono text-[11px] text-slate-400">{sid}</p>
        </div>
        <Link
          href="/dashboard"
          className="rounded border border-slate-200 px-2.5 py-1 text-xs text-brand-dark hover:bg-slate-50"
        >
          ← dashboard
        </Link>
      </div>

      {/* segment summary + WTP */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Customer segment (anonymised)">
          <dl className="space-y-1 text-xs text-slate-600">
            <Row k="City tier" v={`Tier ${cfg.city_tier}`} />
            <Row k="Device category" v={DEVICE_LABEL[cfg.device_type] ?? cfg.device_type} />
            <Row k="Payment preference" v={cfg.payment_method_preference} />
            <Row k="Trust score band" v={trustBand(cfg.cross_merchant_trust_score)} />
            <Row k="Network" v={cfg.ip_type ?? "residential"} />
          </dl>
        </Card>

        <Card title="WTP decision">
          {res ? (
            <div className="space-y-1 text-xs text-slate-600">
              <p className="text-2xl font-bold text-brand-dark">
                ×{res.wtp_multiplier.toFixed(3)}
              </p>
              <Row k="Price shown" v={`${inr(res.final_price)} (${res.price_delta_pct >= 0 ? "+" : ""}${res.price_delta_pct.toFixed(1)}%)`} />
              <Row k="Offer" v={OFFER_LABEL[res.offer_type] ?? res.offer_type} />
              <Row k="Confidence" v={res.confidence} />
              <Row k="Latency" v={`${res.latency_ms.toFixed(0)} ms`} />
            </div>
          ) : (
            <p className="text-xs text-slate-400">
              Session is <strong>{session.status}</strong> — no pricing decision
              yet. Open the customer link and hit “See my price”.
            </p>
          )}
        </Card>

        <Card title="Revenue vs flat pricing (segment)">
          {seg?.revenue_simulation ? (
            <div className="space-y-1 text-xs text-slate-600">
              <p className="text-2xl font-bold text-brand-dark">
                {seg.revenue_simulation.pct_lift >= 0 ? "+" : ""}
                {seg.revenue_simulation.pct_lift.toFixed(1)}%
              </p>
              <Row k="WTP pricing" v={inr(seg.revenue_simulation.expected_revenue_wtp_pricing)} />
              <Row k="Flat pricing" v={inr(seg.revenue_simulation.expected_revenue_flat_pricing)} />
              <Row k="Abs. lift" v={inr(seg.revenue_simulation.absolute_lift)} />
            </div>
          ) : (
            <p className="text-xs text-slate-400">not enough data yet</p>
          )}
        </Card>
      </div>

      {/* SHAP waterfall */}
      <Card title="SHAP waterfall — how each signal moved the WTP">
        {shapAll.length ? (
          <ShapWaterfall
            baseValue={baseValue}
            contributions={shapAll}
            predicted={res?.wtp_multiplier}
          />
        ) : (
          <p className="text-xs text-slate-400">available after the session is priced</p>
        )}
      </Card>

      {/* conversion curve */}
      <Card title="Conversion probability across price points (segment posterior)">
        {seg ? (
          <ConversionCurve
            curve={seg.conversion_curve}
            chosenMultiplier={res?.effective_multiplier}
            height={240}
          />
        ) : (
          <p className="text-xs text-slate-400">loading…</p>
        )}
      </Card>

      {/* segment posterior */}
      <Card title="Segment statistics (Bayesian, updated per decision)">
        {seg ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1 text-xs text-slate-600">
              <Row k="Customers like this seen" v={String(seg.n_customers_like_this)} />
              <Row k="Observations used" v={String(seg.n_observations)} />
              <Row
                k="Posterior WTP mean"
                v={`×${seg.posterior.mean_wtp.toFixed(3)}`}
              />
              <Row
                k="95% credible interval"
                v={`[${seg.posterior.ci_95[0].toFixed(3)} – ${seg.posterior.ci_95[1].toFixed(3)}]`}
              />
              <Row
                k="Prior"
                v={`×${seg.prior.mean.toFixed(2)} (sd ${seg.prior.sd})`}
              />
              {seg.observed.mean_wtp != null && (
                <Row
                  k="Raw observed mean"
                  v={`×${seg.observed.mean_wtp.toFixed(3)}`}
                />
              )}
            </div>
            <PosteriorBar
              lo={seg.posterior.ci_95[0]}
              mean={seg.posterior.mean_wtp}
              hi={seg.posterior.ci_95[1]}
              shown={res?.effective_multiplier}
            />
          </div>
        ) : (
          <p className="text-xs text-slate-400">loading…</p>
        )}
      </Card>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="mb-2 text-xs font-semibold text-slate-500">{title}</p>
      {children}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-400">{k}</dt>
      <dd className="font-medium text-slate-700">{v}</dd>
    </div>
  );
}

function PosteriorBar({
  lo,
  mean,
  hi,
  shown,
}: {
  lo: number;
  mean: number;
  hi: number;
  shown?: number;
}) {
  const min = 0.85;
  const max = 1.25;
  const p = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <div className="relative h-16">
      <div className="absolute left-0 right-0 top-8 h-1 rounded bg-slate-200" />
      <div
        className="absolute top-8 h-1 rounded bg-brand/40"
        style={{ left: `${p(lo)}%`, width: `${p(hi) - p(lo)}%` }}
      />
      <div
        className="absolute top-8 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand"
        style={{ left: `${p(mean)}%` }}
      />
      {shown != null && (
        <div
          className="absolute top-5 h-6 w-0.5 -translate-x-1/2 bg-ink"
          style={{ left: `${p(shown)}%` }}
          title={`price shown ×${shown.toFixed(3)}`}
        />
      )}
      <span className="absolute left-0 top-10 text-[9px] text-slate-400">×{min}</span>
      <span className="absolute right-0 top-10 text-[9px] text-slate-400">×{max}</span>
      <span
        className="absolute top-0 -translate-x-1/2 text-[9px] text-brand-dark"
        style={{ left: `${p(mean)}%` }}
      >
        posterior ×{mean.toFixed(3)}
      </span>
    </div>
  );
}
