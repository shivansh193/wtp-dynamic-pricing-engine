"use client";

import { useEffect, useState } from "react";
import { CheckoutForm } from "@/components/CheckoutForm";
import { DynamicCheckout } from "@/components/DynamicCheckout";
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
    const payload = signalsFromConfig(derived, sessionId);
    // one retry - the backend may be a free-tier instance waking from sleep
    let lastErr: any = null;
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const r = await personalize(payload);
        const wait = Math.max(0, 1000 - (Date.now() - started));
        setTimeout(() => {
          setResult(r);
          setPhase("reveal");
        }, wait);
        return;
      } catch (e: any) {
        lastErr = e;
        if (attempt === 0) await new Promise((res) => setTimeout(res, 1500));
      }
    }
    setErr(
      /failed to fetch|networkerror|503/i.test(String(lastErr?.message))
        ? "The pricing service is waking up — give it a few seconds and tap “See my price” again."
        : lastErr?.message || "Something went wrong.",
    );
    setPhase("error");
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
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-center text-sm text-amber-800">
            <p>{err ?? "Something went wrong."}</p>
            {session && (
              <button
                onClick={() => {
                  setErr(null);
                  setPhase("form");
                }}
                className="mt-3 rounded-md bg-ink px-4 py-1.5 text-xs font-medium text-white"
              >
                Back to form
              </button>
            )}
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

        {phase === "reveal" && result && session && (
          <DynamicCheckout
            result={result}
            sessionId={sessionId}
            config={session.config}
            sessionCreatedAt={session.created_at}
            onResult={setResult}
          />
        )}
      </div>
    </div>
  );
}
