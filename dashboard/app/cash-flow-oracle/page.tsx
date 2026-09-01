"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getOracleForecast, getOracleMerchants } from "@/lib/cfoApi";
import type { OracleForecast, OracleMerchant } from "@/lib/cfoTypes";
import { AnomalyFeed } from "@/components/cfo/AnomalyFeed";
import { CashForecastHero } from "@/components/cfo/CashForecastHero";
import { CreditRecommendationCard } from "@/components/cfo/CreditRecommendationCard";
import { FingerprintHeatmap } from "@/components/cfo/FingerprintHeatmap";
import { MerchantSelector } from "@/components/cfo/MerchantSelector";
import { PeerBenchmarking } from "@/components/cfo/PeerBenchmarking";
import { RegimePanel } from "@/components/cfo/RegimePanel";
import { ScenarioSimulator } from "@/components/cfo/ScenarioSimulator";
import { WhatsAppAlertPreview } from "@/components/cfo/WhatsAppAlertPreview";
import { ErrorNote, PanelSkeleton } from "@/components/cfo/Skeleton";

function Label({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
      {children}
    </h2>
  );
}

export default function CashFlowOraclePage() {
  const [merchants, setMerchants] = useState<OracleMerchant[] | null>(null);
  const [merchantsErr, setMerchantsErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>("");

  const [forecast, setForecast] = useState<OracleForecast | null>(null);
  const [fcErr, setFcErr] = useState<string | null>(null);
  const [fcLoading, setFcLoading] = useState(false);

  const loadMerchants = useCallback(() => {
    setMerchantsErr(null);
    getOracleMerchants()
      .then((r) => {
        setMerchants(r.merchants);
        setSelected((cur) => cur || r.merchants[0]?.merchant_id || "");
      })
      .catch((e) => setMerchantsErr((e as Error).message));
  }, []);

  useEffect(loadMerchants, [loadMerchants]);

  const loadForecast = useCallback((id: string) => {
    if (!id) return;
    setFcLoading(true);
    setFcErr(null);
    setForecast(null);
    getOracleForecast(id, 60)
      .then(setForecast)
      .catch((e) => setFcErr((e as Error).message))
      .finally(() => setFcLoading(false));
  }, []);

  useEffect(() => {
    if (selected) loadForecast(selected);
  }, [selected, loadForecast]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-base font-semibold text-ink">AI Cash Flow Oracle</h1>
          <p className="text-xs text-zinc-400">
            30–60 day settlement forecast · stress detection · proactive credit
            timing — Razorpay Buildathon Track 04
          </p>
        </div>
        <Link href="/dashboard" className="text-xs text-brand hover:underline">
          ← Track 01: WTP Pricing
        </Link>
      </div>

      {merchantsErr ? (
        <ErrorNote error={merchantsErr} onRetry={loadMerchants} />
      ) : !merchants ? (
        <PanelSkeleton lines={1} />
      ) : (
        <MerchantSelector
          merchants={merchants}
          selected={selected}
          onSelect={setSelected}
        />
      )}

      {/* hero */}
      {fcErr ? (
        <div className="rounded-lg border border-zinc-200 bg-white p-8 text-center">
          <p className="text-sm text-zinc-500">
            Couldn&apos;t load the forecast for this merchant.
          </p>
          <p className="mt-1 text-xs text-zinc-400">{fcErr}</p>
          <button
            onClick={() => loadForecast(selected)}
            className="mt-3 rounded-md bg-brand px-4 py-1.5 text-xs font-semibold text-white"
          >
            Generate forecast
          </button>
        </div>
      ) : fcLoading || !forecast ? (
        <PanelSkeleton chart lines={3} />
      ) : (
        <>
          <CashForecastHero f={forecast} />

          <div className="grid gap-6 lg:grid-cols-2">
            <CreditRecommendationCard f={forecast} />
            <RegimePanel f={forecast} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <WhatsAppAlertPreview merchantId={selected} />
            <ScenarioSimulator merchantId={selected} />
          </div>

          <section>
            <Label>Peer benchmarking</Label>
            <PeerBenchmarking merchantId={selected} />
          </section>

          <section>
            <Label>Anomaly detection</Label>
            <AnomalyFeed merchantId={selected} />
          </section>

          <section>
            <Label>Settlement fingerprint</Label>
            <FingerprintHeatmap merchantId={selected} />
          </section>
        </>
      )}
    </div>
  );
}
