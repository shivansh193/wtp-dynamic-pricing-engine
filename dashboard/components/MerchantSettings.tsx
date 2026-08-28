"use client";

import { useEffect, useState } from "react";
import { getMerchantConfig, resetMerchantConfig, updateMerchantConfig } from "@/lib/api";
import type { MerchantConfig } from "@/lib/types";

/** Merchant-facing pricing rules. Plain-language switches + a few sliders —
 *  changes apply to every new pricing decision immediately. */
export function MerchantSettings({ onChange }: { onChange?: () => void }) {
  const [cfg, setCfg] = useState<MerchantConfig | null>(null);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    getMerchantConfig().then(setCfg).catch(() => {});
  }, []);

  const patch = async (p: Partial<MerchantConfig>) => {
    if (!cfg) return;
    // optimistic
    setCfg({ ...cfg, ...p, offers: { ...cfg.offers, ...(p as any).offers }, trust_weights: { ...cfg.trust_weights, ...(p as any).trust_weights } });
    setSaving(true);
    try {
      const next = await updateMerchantConfig(p);
      setCfg(next);
      setSavedAt(Date.now());
      onChange?.();
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    try {
      setCfg(await resetMerchantConfig());
      setSavedAt(Date.now());
      onChange?.();
    } finally {
      setSaving(false);
    }
  };

  if (!cfg) return null;
  const w = cfg.trust_weights;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3"
      >
        <span className="text-[13px] font-semibold text-zinc-800">
          Pricing rules
          <span className="ml-2 font-normal text-zinc-400">
            {cfg.markup_enabled
              ? `markup on · +${(cfg.max_markup_pct * 100).toFixed(0)}% / −${(cfg.max_discount_pct * 100).toFixed(0)}%`
              : "markup off · discount-only"}
          </span>
        </span>
        <span className="text-xs text-zinc-400">
          {saving ? "saving…" : savedAt ? "saved" : ""} {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="grid gap-6 border-t border-zinc-100 px-5 py-4 md:grid-cols-3">
          {/* price band */}
          <div className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              Price band
            </p>
            <Toggle
              label="Allow above-list pricing"
              hint="Off = a shopper is never charged more than list price."
              checked={cfg.markup_enabled}
              onChange={(v) => patch({ markup_enabled: v })}
            />
            <Slider
              label="Max markup"
              value={cfg.max_markup_pct}
              min={0}
              max={0.15}
              step={0.01}
              fmt={(v) => `+${(v * 100).toFixed(0)}%`}
              onChange={(v) => patch({ max_markup_pct: v })}
              disabled={!cfg.markup_enabled}
            />
            <Slider
              label="Max discount"
              value={cfg.max_discount_pct}
              min={0}
              max={0.1}
              step={0.01}
              fmt={(v) => `−${(v * 100).toFixed(0)}%`}
              onChange={(v) => patch({ max_discount_pct: v })}
            />
            <Slider
              label="Assumed gross margin"
              hint="used for the margin-vs-flat estimate"
              value={cfg.gross_margin}
              min={0.1}
              max={0.8}
              step={0.05}
              fmt={(v) => `${(v * 100).toFixed(0)}%`}
              onChange={(v) => patch({ gross_margin: v })}
            />
          </div>

          {/* perks */}
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              Perks the engine may offer
            </p>
            {(
              [
                ["extended_warranty", "Extended warranty"],
                ["priority_support", "Priority support"],
                ["free_delivery", "Free delivery"],
                ["cashback_5pct", "5% cashback"],
                ["instant_refund", "Instant-refund badge"],
              ] as const
            ).map(([k, label]) => (
              <Toggle
                key={k}
                label={label}
                checked={cfg.offers[k]}
                onChange={(v) => patch({ offers: { [k]: v } } as any)}
              />
            ))}
          </div>

          {/* trust weights */}
          <div className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              Trust score inputs
            </p>
            <Slider
              label="Weight: prepaid history"
              value={w.w_prepaid_order}
              min={0}
              max={2}
              step={0.1}
              fmt={(v) => `×${v.toFixed(1)}`}
              onChange={(v) => patch({ trust_weights: { w_prepaid_order: v } } as any)}
            />
            <Slider
              label="Penalty: return rate"
              value={w.w_return_rate}
              min={0}
              max={1}
              step={0.05}
              fmt={(v) => `×${v.toFixed(2)}`}
              onChange={(v) => patch({ trust_weights: { w_return_rate: v } } as any)}
            />
            <Slider
              label="Bonus: credit-card share"
              value={w.w_credit_card_share}
              min={0}
              max={30}
              step={1}
              fmt={(v) => `+${v.toFixed(0)}`}
              onChange={(v) => patch({ trust_weights: { w_credit_card_share: v } } as any)}
            />
            <Slider
              label="Penalty: COD share"
              value={w.w_cod_share}
              min={0}
              max={30}
              step={1}
              fmt={(v) => `−${v.toFixed(0)}`}
              onChange={(v) => patch({ trust_weights: { w_cod_share: v } } as any)}
            />
            <Slider
              label="Penalty: VPN / public network"
              value={w.w_vpn_penalty}
              min={0}
              max={40}
              step={1}
              fmt={(v) => `−${v.toFixed(0)}`}
              onChange={(v) => patch({ trust_weights: { w_vpn_penalty: v } } as any)}
            />
            <button
              onClick={reset}
              className="text-[11px] text-zinc-400 underline underline-offset-2 hover:text-zinc-600"
            >
              reset all rules to defaults
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-2">
      <div>
        <span className="text-xs text-zinc-700">{label}</span>
        {hint && <p className="text-[10px] text-zinc-400">{hint}</p>}
      </div>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`mt-0.5 relative h-4 w-8 shrink-0 rounded-full transition ${
          checked ? "bg-brand" : "bg-zinc-300"
        }`}
      >
        <span
          className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition ${
            checked ? "left-4" : "left-0.5"
          }`}
        />
      </button>
    </div>
  );
}

function Slider({
  label,
  hint,
  value,
  min,
  max,
  step,
  fmt,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  fmt: (v: number) => string;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <label className={`block ${disabled ? "opacity-40" : ""}`}>
      <span className="flex items-center justify-between text-xs text-zinc-700">
        {label}
        <span className="tabular-nums text-zinc-500">{fmt(value)}</span>
      </span>
      {hint && <span className="block text-[10px] text-zinc-400">{hint}</span>}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full accent-brand"
      />
    </label>
  );
}
