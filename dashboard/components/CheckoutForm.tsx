"use client";

import { useEffect, useRef, useState } from "react";
import { deriveConfig } from "@/lib/api";
import { PRODUCT } from "@/lib/profiles";
import type { SessionConfig } from "@/lib/types";
import { PaymentSplitEditor, type Split, evenSplit } from "./PaymentSplitEditor";

const DEVICES = ["Android_budget", "Android_premium", "iPhone", "Desktop"] as const;

export interface Knobs {
  pin_code: string;
  device_type: (typeof DEVICES)[number];
  payment_split: Split;
  prepaid_orders: number;
  return_rate: number;
  vpn: boolean;
}

export function CheckoutForm({
  initial,
  onSubmit,
  submitting,
}: {
  initial: SessionConfig;
  onSubmit: (derived: SessionConfig) => void;
  submitting: boolean;
}) {
  const [knobs, setKnobs] = useState<Knobs>({
    pin_code: initial.pin_code,
    device_type: initial.device_type,
    payment_split: (initial.payment_split as Split) ?? evenSplit(),
    prepaid_orders: initial.prepaid_orders,
    return_rate: initial.return_rate,
    vpn: initial.vpn,
  });
  const [derived, setDerived] = useState<SessionConfig>(initial);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await deriveConfig({
          pin_code: knobs.pin_code,
          device_type: knobs.device_type,
          payment_split: knobs.payment_split,
          prepaid_orders: knobs.prepaid_orders,
          return_rate: knobs.return_rate,
          vpn: knobs.vpn,
        });
        setDerived(r.config as SessionConfig);
      } catch {
        /* keep last */
      }
    }, 250);
    return () => clearTimeout(timer.current);
  }, [knobs]);

  const set = (p: Partial<Knobs>) => setKnobs((k) => ({ ...k, ...p }));

  return (
    <div className="mx-auto max-w-lg space-y-5">
      <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-slate-100 text-2xl">
          {PRODUCT.emoji}
        </div>
        <div>
          <p className="text-sm font-medium text-ink">{PRODUCT.name}</p>
          <p className="text-xs text-slate-500">
            {PRODUCT.brand} · sold by {PRODUCT.seller}
          </p>
          <p className="text-xs text-slate-400">
            MRP ₹{PRODUCT.list_price.toLocaleString("en-IN")}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <p className="mb-3 text-xs text-slate-500">
          These help us personalise your experience.
        </p>

        <div className="space-y-4">
          <label className="block">
            <span className="text-xs font-medium text-slate-600">Delivery pincode</span>
            <input
              className="mt-1 w-full rounded-md border border-slate-200 px-2.5 py-1.5 text-sm"
              value={knobs.pin_code}
              onChange={(e) => set({ pin_code: e.target.value })}
              inputMode="numeric"
            />
            <span className="mt-0.5 block text-[11px] text-slate-400">
              detected: {derived.city} · Tier {derived.city_tier}
            </span>
          </label>

          <Radio
            label="Device"
            options={DEVICES as unknown as string[]}
            value={knobs.device_type}
            onChange={(v) => set({ device_type: v as Knobs["device_type"] })}
          />

          <div>
            <span className="text-xs font-medium text-slate-600">
              How you usually pay
            </span>
            <div className="mt-1.5">
              <PaymentSplitEditor
                value={knobs.payment_split}
                onChange={(s) => set({ payment_split: s })}
                compact
              />
            </div>
          </div>

          <label className="block">
            <span className="text-xs font-medium text-slate-600">
              Past prepaid orders: {knobs.prepaid_orders}
            </span>
            <input
              type="range"
              min={0}
              max={50}
              value={knobs.prepaid_orders}
              onChange={(e) => set({ prepaid_orders: Number(e.target.value) })}
              className="w-full accent-brand"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-slate-600">
              Return rate: {(knobs.return_rate * 100).toFixed(0)}%
            </span>
            <input
              type="range"
              min={0}
              max={0.5}
              step={0.01}
              value={knobs.return_rate}
              onChange={(e) => set({ return_rate: Number(e.target.value) })}
              className="w-full accent-brand"
            />
          </label>

          <label className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-600">
              On a VPN / public network
            </span>
            <button
              role="switch"
              aria-checked={knobs.vpn}
              onClick={() => set({ vpn: !knobs.vpn })}
              className={`relative h-5 w-9 rounded-full transition ${
                knobs.vpn ? "bg-brand" : "bg-slate-300"
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition ${
                  knobs.vpn ? "left-4" : "left-0.5"
                }`}
              />
            </button>
          </label>

          <div className="rounded-md bg-slate-50 px-3 py-2 text-[11px] text-slate-500">
            derived trust score{" "}
            <strong className="text-slate-700">
              {derived.cross_merchant_trust_score}
            </strong>{" "}
            · COD completion {(derived.cod_completion_rate * 100).toFixed(0)}%
            {knobs.vpn && (
              <span className="ml-1 rounded bg-red-50 px-1 text-red-600">
                VPN — trust reduced
              </span>
            )}
          </div>
        </div>

        <button
          onClick={() => onSubmit(derived)}
          disabled={submitting}
          className="mt-4 w-full rounded-md bg-ink py-2.5 text-sm font-semibold text-white disabled:opacity-60"
        >
          {submitting ? "personalising…" : "See my price"}
        </button>
      </div>
    </div>
  );
}

function Radio({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <fieldset>
      <span className="text-xs font-medium text-slate-600">{label}</span>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {options.map((o) => (
          <button
            key={o}
            onClick={() => onChange(o)}
            className={`rounded-md px-2.5 py-1 text-xs ring-1 ${
              value === o
                ? "bg-brand text-white ring-brand"
                : "bg-white text-slate-600 ring-slate-200"
            }`}
          >
            {o}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
