"use client";

import { useEffect, useRef, useState } from "react";
import { DynamicCheckout } from "@/components/DynamicCheckout";
import { getSession, personalize } from "@/lib/api";
import { signalsFromConfig } from "@/lib/profiles";
import type { PricingResponse, SessionConfig, SessionInfo } from "@/lib/types";

type Phase = "loading" | "personalising" | "reveal" | "error";

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
  const started = useRef(false); // guards against React StrictMode's double effect in dev

  useEffect(() => {
    if (started.current) return;
    started.current = true;
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
        // seller already set this shopper's profile when generating the link -
        // price it immediately instead of asking them to confirm the same
        // fields again
        submit(s.config);
      })
      .catch((e) => {
        setErr(e.message);
        setPhase("error");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        ? "The pricing service is waking up — give it a few seconds and tap “Try again”."
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
                  submit(session.config);
                }}
                className="mt-3 rounded-md bg-ink px-4 py-1.5 text-xs font-medium text-white"
              >
                Try again
              </button>
            )}
          </div>
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
