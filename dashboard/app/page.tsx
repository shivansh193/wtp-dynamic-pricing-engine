"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckoutPanel } from "@/components/CheckoutPanel";
import { ProfileEditor } from "@/components/ProfileEditor";
import { MetricsPanel } from "@/components/MetricsPanel";
import { IpEnrichmentVisualizer } from "@/components/IpEnrichmentVisualizer";
import { personalize } from "@/lib/api";
import { CUSTOMER_A, CUSTOMER_B, IP_SAMPLES, PRODUCT } from "@/lib/profiles";
import type { CustomerSignals, PricingResponse } from "@/lib/types";

interface PanelState {
  result: PricingResponse | null;
  loading: boolean;
  error: string | null;
  lastLatency: number | null;
}

const INIT: PanelState = { result: null, loading: true, error: null, lastLatency: null };

function useDebouncedPersonalize(
  profile: CustomerSignals,
  onDone: () => void,
): PanelState {
  const [state, setState] = useState<PanelState>(INIT);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    setState((s) => ({ ...s, loading: true }));
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await personalize(profile);
        setState({ result: r, loading: false, error: null, lastLatency: r.latency_ms });
        onDone();
      } catch (e: any) {
        setState((s) => ({ ...s, loading: false, error: e.message }));
      }
    }, 350);
    return () => clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(profile)]);

  return state;
}

export default function Page() {
  const [profileA, setProfileA] = useState<CustomerSignals>(CUSTOMER_A);
  const [profileB, setProfileB] = useState<CustomerSignals>(CUSTOMER_B);
  const [vpnA, setVpnA] = useState(false);
  const [vpnB, setVpnB] = useState(true); // B starts on a VPN egress IP
  const [metricsKey, setMetricsKey] = useState(0);

  const bumpMetrics = useCallback(() => setMetricsKey((k) => k + 1), []);

  const stateA = useDebouncedPersonalize(profileA, bumpMetrics);
  const stateB = useDebouncedPersonalize(profileB, bumpMetrics);

  const patch = (
    setter: typeof setProfileA,
  ) => (p: Partial<CustomerSignals>) => setter((prev) => ({ ...prev, ...p }));

  const toggleVpn =
    (which: "A" | "B") => (on: boolean) => {
      const setter = which === "A" ? setProfileA : setProfileB;
      const setVpn = which === "A" ? setVpnA : setVpnB;
      setVpn(on);
      setter((prev) => ({
        ...prev,
        ip_type: on ? "vpn" : "residential",
        ip: on ? IP_SAMPLES.vpn : IP_SAMPLES.residential,
      }));
    };

  const spread = useMemo(() => {
    if (!stateA.result || !stateB.result) return null;
    return stateA.result.final_price - stateB.result.final_price;
  }, [stateA.result, stateB.result]);

  return (
    <div className="space-y-8">
      <section>
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 className="text-base font-semibold text-ink">
              Same product, two shoppers
            </h2>
            <p className="text-xs text-slate-500">
              {PRODUCT.name} — list price ₹{PRODUCT.list_price.toLocaleString("en-IN")}.
              Each checkout is personalised in real time by the pricing engine.
            </p>
          </div>
          {spread != null && (
            <p className="text-xs text-slate-500">
              price spread A − B:{" "}
              <strong className="text-ink">
                ₹{spread.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </strong>
            </p>
          )}
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <CheckoutPanel
            title="Customer A — high trust"
            subtitle="iPhone · Mumbai (Tier 1) · Credit Card · trust 92 · 3-year account"
            accent="emerald"
            result={stateA.result}
            loading={stateA.loading}
            error={stateA.error}
          />
          <CheckoutPanel
            title="Customer B — low trust"
            subtitle="Budget Android · Patna (Tier 3) · COD · trust 31 · 6-month account"
            accent="amber"
            result={stateB.result}
            loading={stateB.loading}
            error={stateB.error}
          />
        </div>
      </section>

      <section className="grid gap-5 md:grid-cols-2">
        <ProfileEditor
          which="A"
          profile={profileA}
          latencyMs={stateA.lastLatency}
          onChange={patch(setProfileA)}
        />
        <ProfileEditor
          which="B"
          profile={profileB}
          latencyMs={stateB.lastLatency}
          onChange={patch(setProfileB)}
        />
      </section>

      <section className="grid gap-5 md:grid-cols-2">
        <IpEnrichmentVisualizer
          label="Customer A"
          result={stateA.result}
          vpnOn={vpnA}
          onToggleVpn={toggleVpn("A")}
        />
        <IpEnrichmentVisualizer
          label="Customer B"
          result={stateB.result}
          vpnOn={vpnB}
          onToggleVpn={toggleVpn("B")}
        />
      </section>

      <section>
        <MetricsPanel refreshKey={metricsKey} />
      </section>
    </div>
  );
}
