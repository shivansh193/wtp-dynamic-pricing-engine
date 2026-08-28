"use client";

import { useState } from "react";
import { createSession } from "@/lib/api";
import { PRESET_LABELS } from "@/lib/profiles";
import type { CustomSessionFields, Preset, SessionCreateResponse } from "@/lib/types";
import { CopyField } from "./CopyField";
import { PaymentSplitEditor, type Split, evenSplit } from "./PaymentSplitEditor";

const PRESETS: Preset[] = ["random", "high", "mid", "low", "custom"];
const DEVICES = ["Android_budget", "Android_premium", "iPhone", "Desktop"] as const;

export function LinkGenerator({
  onCreated,
}: {
  onCreated?: (s: SessionCreateResponse) => void;
}) {
  const [preset, setPreset] = useState<Preset>("high");
  const [custom, setCustom] = useState<CustomSessionFields & { payment_split: Split }>({
    pin_code: "560001",
    device_type: "iPhone",
    payment_split: evenSplit(),
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
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-card">
      <div className="grid gap-5 md:grid-cols-[260px_1fr]">
        {/* controls */}
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs text-zinc-500">Profile</span>
            <select
              className="mt-1 w-full rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
              value={preset}
              onChange={(e) => setPreset(e.target.value as Preset)}
            >
              {PRESETS.map((p) => (
                <option key={p} value={p}>
                  {PRESET_LABELS[p].label}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-[11px] text-zinc-400">
              {PRESET_LABELS[preset].blurb}
            </span>
          </label>

          {preset === "custom" && (
            <div className="space-y-2.5 rounded-md bg-zinc-50 p-3">
              <label className="block">
                <span className="text-[11px] text-zinc-500">
                  Pincode (sets city tier)
                </span>
                <input
                  className="mt-0.5 w-full rounded border border-zinc-200 px-2 py-1 text-xs"
                  value={custom.pin_code ?? ""}
                  onChange={(e) => setCustom({ ...custom, pin_code: e.target.value })}
                  placeholder="400001"
                />
              </label>

              <div>
                <span className="text-[11px] text-zinc-500">Device</span>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {DEVICES.map((d) => (
                    <button
                      key={d}
                      onClick={() => setCustom({ ...custom, device_type: d })}
                      className={`rounded px-2 py-0.5 text-[11px] ring-1 ${
                        custom.device_type === d
                          ? "bg-brand text-white ring-brand"
                          : "bg-white text-zinc-600 ring-zinc-200"
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <span className="text-[11px] text-zinc-500">Payment mix</span>
                <div className="mt-1">
                  <PaymentSplitEditor
                    value={custom.payment_split}
                    onChange={(s) => setCustom({ ...custom, payment_split: s })}
                    compact
                  />
                </div>
              </div>

              <label className="block">
                <span className="text-[11px] text-zinc-500">
                  Prepaid orders: {custom.prepaid_orders}
                </span>
                <input
                  type="range"
                  min={0}
                  max={50}
                  value={custom.prepaid_orders ?? 0}
                  onChange={(e) =>
                    setCustom({ ...custom, prepaid_orders: Number(e.target.value) })
                  }
                  className="w-full accent-brand"
                />
              </label>

              <label className="block">
                <span className="text-[11px] text-zinc-500">
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
                  className="w-full accent-brand"
                />
              </label>

              <label className="flex items-center gap-2 text-[11px] text-zinc-600">
                <input
                  type="checkbox"
                  checked={!!custom.vpn}
                  onChange={(e) => setCustom({ ...custom, vpn: e.target.checked })}
                  className="accent-brand"
                />
                On a VPN / public network
              </label>
            </div>
          )}

          <button
            onClick={generate}
            disabled={loading}
            className="w-full rounded-md bg-brand py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-60"
          >
            {loading ? "generating…" : "Generate link"}
          </button>
          {err && <p className="text-xs text-red-600">{err}</p>}
        </div>

        {/* result */}
        <div className="rounded-md border border-zinc-100 bg-zinc-50/60 p-4">
          {!result ? (
            <p className="text-xs text-zinc-400">
              A shareable checkout link, a merchant-view link, and a QR code for
              the phone demo will appear here.
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-[1fr_136px]">
              <div className="space-y-3">
                <CopyField label="Customer link" value={result.customer_url} />
                <CopyField label="Merchant view" value={result.merchant_url} />
                <div className="flex flex-wrap gap-1 text-[11px]">
                  <Tag>{PRESET_LABELS[result.preset as Preset]?.label ?? result.preset}</Tag>
                  <Tag>T{cfg?.city_tier} · {cfg?.city}</Tag>
                  <Tag>{cfg?.device_type}</Tag>
                  <Tag>trust {cfg?.cross_merchant_trust_score}</Tag>
                  <Tag>{cfg?.prepaid_orders} prepaid</Tag>
                  <Tag>{Math.round((cfg?.return_rate ?? 0) * 100)}% returns</Tag>
                  {cfg?.vpn && <Tag danger>VPN</Tag>}
                </div>
                <p className="font-mono text-[10px] text-zinc-400">
                  {result.session_id} · {result.segment_key}
                </p>
              </div>
              {result.qr_code_base64 ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={result.qr_code_base64}
                  alt="Customer link QR"
                  className="h-[136px] w-[136px] self-start rounded border border-zinc-200 bg-white p-1"
                />
              ) : (
                <div className="flex h-[136px] items-center justify-center rounded border border-dashed border-zinc-300 text-[10px] text-zinc-400">
                  QR unavailable
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Tag({ children, danger }: { children: React.ReactNode; danger?: boolean }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 ring-1 ${
        danger
          ? "bg-red-50 text-red-700 ring-red-200"
          : "bg-white text-zinc-600 ring-zinc-200"
      }`}
    >
      {children}
    </span>
  );
}
