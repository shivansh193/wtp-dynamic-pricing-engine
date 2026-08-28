"use client";

import { useEffect, useState } from "react";
import { CheckoutForm } from "@/components/CheckoutForm";
import { PriceReveal } from "@/components/PriceReveal";
import { getSession, personalize } from "@/lib/api";
import { PRESET_LABELS, signalsFromConfig } from "@/lib/profiles";
import type { PricingResponse, Preset, SessionConfig, SessionInfo } from "@/lib/types";

type Phase = "loading" | "form" | "personalising" | "reveal" | "error";

export default function CheckoutPage({
  params,
}: {
  params: { session_id: string };
}) {
  const sessionId = params.session_id;
  const [phase, setPhase] = useState<Phase>("loading");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [result, setResult] = useState<PricingResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getSession(sessionId)
      .then((s) => {
        setSession(s);
        if (s.status === "priced" || s.status === "converted") {
          if (s.result) {
            setResult(s.result);
            setPhase("reveal");
            return;
          }
        }
        setPhase("form");
      })
      .catch((e) => {
        setErr(e.message);
        setPhase("error");
      });
  }, [sessionId]);

  const submit = async (derived: SessionConfig) => {
    setPhase("personalising");
    const started = Date.now();
    try {
      const r = await personalize(signalsFromConfig(derived, sessionId));
      // hold the "personalising" screen for at least ~1s for the reveal effect
      const wait = Math.max(0, 1000 - (Date.now() - started));
      setTimeout(() => {
        setResult(r);
        setPhase("reveal");
      }, wait);
    } catch (e: any) {
      setErr(e.message);
      setPhase("error");
    }
  };

  return (
    <div className="py-4">
      <div className="mx-auto max-w-lg px-4">
        <div className="mb-6 text-center">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
            RunHub checkout
          </p>
          {session && phase === "form" && (
            <p className="text-[11px] text-slate-400">
              pre-filled from “
              {PRESET_LABELS[session.preset as Preset]?.label ?? session.preset}”
              — adjust anything before you continue
            </p>
          )}
        </div>

        {phase === "loading" && (
          <p className="text-center text-sm text-slate-400">loading session…</p>
        )}

        {phase === "error" && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center text-sm text-red-700">
            {err ?? "Something went wrong."}
          </div>
        )}

        {phase === "form" && session && (
          <CheckoutForm
            initial={session.config}
            onSubmit={submit}
            submitting={false}
          />
        )}

        {phase === "personalising" && (
          <div className="mx-auto max-w-sm rounded-xl border border-slate-200 bg-white p-10 text-center">
            <div className="mx-auto mb-4 h-3 w-3 animate-ping rounded-full bg-brand" />
            <p className="text-sm text-slate-600">personalising your checkout…</p>
            <div className="shimmer mx-auto mt-4 h-8 w-40 rounded bg-slate-200" />
          </div>
        )}

        {phase === "reveal" && result && (
          <PriceReveal result={result} sessionId={sessionId} />
        )}
      </div>
    </div>
  );
}
