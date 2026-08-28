"use client";

import { useState } from "react";
import { createSession } from "@/lib/api";
import { PRESET_LABELS } from "@/lib/profiles";
import type { CustomSessionFields, Preset, SessionCreateResponse } from "@/lib/types";
import { CopyField } from "./CopyField";

const PRESETS: Preset[] = ["random", "high", "mid", "low", "custom"];
const DEVICES = ["Android_budget", "Android_premium", "iPhone", "Desktop"] as const;
const PAYMENTS = ["UPI", "Credit_Card", "Debit_Card", "COD", "Wallet"] as const;

export function LinkGenerator({ onCreated }: { onCreated?: (s: SessionCreateResponse) => void }) {
  const [preset, setPreset] = useState<Preset>("high");
  const [custom, setCustom] = useState<CustomSessionFields>({
    pin_code: "560001",
    device_type: "iPhone",
    payment_method_preference: "UPI",
    prepaid_orders: 20,
    return_rate: 0.1,
    vpn: false,
  });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<SessionCreateResponse | null>(null);

  const generate = async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await createSession(
        preset,
        preset === "custom" ? custom : undefined,
      );
      setResult(r);
      onCreated?.(r);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  const cfg = result?.config;

  return (
    <section className="rounded-xl border border-brand/30 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <span className="rounded-md bg-brand px-2 py-0.5 text-xs font-semibold text-white">
          demo
        </span>
        <h2 className="text-base font-semibold text-ink">Generate Customer Link</h2>
      </div>

      <div className="grid gap-4 md:grid-cols-[280px_1fr]">
        {/* left: controls */}
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-slate-500">Default profile</span>
            <select
              className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm"
              value={preset}
              onChange={(e) => setPreset(e.target.value as Preset)}
            >
              {PRESETS.map((p) => (
                <option key={p} value={p}>
                  {PRESET_LABELS[p].label}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-[11px] text-slate-400">
              {PRESET_LABELS[preset].blurb}
            </span>
          </label>

          {preset === "custom" && (
            <div className="space-y-2 rounded-lg bg-slate-50 p-3">
              <label className="block">
                <span className="text-[11px] text-slate-500">
                  Pincode (auto-detects city tier)
                </span>
                <input
                  className="mt-0.5 w-full rounded border border-slate-200 px-2 py-1 text-xs"
                  value={custom.pin_code ?? ""}
                  onChange={(e) => setCustom({ ...custom, pin_code: e.target.value })}
                  placeholder="e.g. 400001"
                />
              </label>

              <fieldset>
                <span className="text-[11px] text-slate-500">Device type</span>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {DEVICES.map((d) => (
                    <button
                      key={d}
                      onClick={() => setCustom({ ...custom, device_type: d })}
                      className={`rounded px-2 py-0.5 text-[11px] ring-1 ${
                        custom.device_type === d
                          ? "bg-brand text-white ring-brand"
                          : "bg-white text-slate-600 ring-slate-200"
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </fieldset>

              <fieldset>
                <span className="text-[11px] text-slate-500">Payment preference</span>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {PAYMENTS.map((p) => (
                    <button
                      key={p}
                      onClick={() =>
                        setCustom({ ...custom, payment_method_preference: p })
                      }
                      className={`rounded px-2 py-0.5 text-[11px] ring-1 ${
                        custom.payment_method_preference === p
                          ? "bg-brand text-white ring-brand"
                          : "bg-white text-slate-600 ring-slate-200"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </fieldset>

              <label className="block">
                <span className="text-[11px] text-slate-500">
                  Past prepaid orders: {custom.prepaid_orders}
                </span>
                <input
                  type="range"
                  min={0}
                  max={50}
                  value={custom.prepaid_orders ?? 0}
                  onChange={(e) =>
                    setCustom({ ...custom, prepaid_orders: Number(e.target.value) })
                  }
                  className="w-full"
                />
              </label>

              <label className="block">
                <span className="text-[11px] text-slate-500">
                  Return rate: {((custom.return_rate ?? 0) * 100).toFixed(0)}%
                </span>
                <input
                  type="range"
                  min={0}
                  max={0.5}
                  step={0.01}
                  value={custom.return_rate ?? 0}
                  onChange={(e) =>
                    setCustom({ ...custom, return_rate: Number(e.target.value) })
                  }
                  className="w-full"
                />
              </label>

              <label className="flex items-center gap-2 text-[11px] text-slate-600">
                <input
                  type="checkbox"
                  checked={!!custom.vpn}
                  onChange={(e) => setCustom({ ...custom, vpn: e.target.checked })}
                />
                VPN / public network
              </label>
            </div>
          )}

          <button
            onClick={generate}
            disabled={loading}
            className="w-full rounded-md bg-brand py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
          >
            {loading ? "generating…" : "Generate Link"}
          </button>
          {err && <p className="text-xs text-red-600">{err}</p>}
        </div>

        {/* right: result */}
        <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-4">
          {!result ? (
            <p className="text-xs text-slate-400">
              Pick a profile and hit Generate — you&apos;ll get a shareable
              checkout link, a merchant view link, and a QR code for the
              phone demo.
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-[1fr_150px]">
              <div className="space-y-3">
                <CopyField label="Customer link" value={result.customer_url} />
                <CopyField label="Merchant view link" value={result.merchant_url} />
                <div className="flex flex-wrap gap-1.5 text-[11px]">
                  <Tag>{PRESET_LABELS[result.preset as Preset]?.label ?? result.preset}</Tag>
                  <Tag>Tier {cfg?.city_tier} · {cfg?.city}</Tag>
                  <Tag>{cfg?.device_type}</Tag>
                  <Tag>{cfg?.payment_method_preference}</Tag>
                  <Tag>trust {cfg?.cross_merchant_trust_score}</Tag>
                  <Tag>{cfg?.prepaid_orders} prepaid</Tag>
                  <Tag>{Math.round((cfg?.return_rate ?? 0) * 100)}% returns</Tag>
                  {cfg?.vpn && <Tag danger>VPN</Tag>}
                </div>
                <p className="text-[10px] text-slate-400">
                  session {result.session_id} · segment {result.segment_key}
                </p>
              </div>
              {result.qr_code_base64 ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={result.qr_code_base64}
                  alt="Customer link QR"
                  className="h-[150px] w-[150px] self-start rounded-md border border-slate-200 bg-white p-1"
                />
              ) : (
                <div className="flex h-[150px] items-center justify-center rounded-md border border-dashed border-slate-300 text-[10px] text-slate-400">
                  QR unavailable
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Tag({ children, danger }: { children: React.ReactNode; danger?: boolean }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 ring-1 ${
        danger
          ? "bg-red-50 text-red-700 ring-red-200"
          : "bg-white text-slate-600 ring-slate-200"
      }`}
    >
      {children}
    </span>
  );
}
