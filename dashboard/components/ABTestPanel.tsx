"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { runAbTest } from "@/lib/api";
import { inr } from "@/lib/profiles";
import type { AbTestResult } from "@/lib/types";

const DEVICES = ["Android_budget", "Android_premium", "iPhone", "Desktop"];
const CATEGORIES = ["fashion", "electronics", "grocery", "home", "beauty"];
const FRICTION_LABEL: Record<string, string> = {
  price_sensitivity: "Price sensitivity",
  trust_deficit: "Trust deficit",
  decision_paralysis: "Decision paralysis",
  payment_friction: "Payment friction",
  delivery_anxiety: "Delivery anxiety",
  urgency_insensitive: "Urgency-insensitive",
};

/** Synthetic control (flat price) vs treatment (WTP price + friction-aware
 *  intervention) experiment for a segment. Backed by POST /simulate/ab_test —
 *  a real synthetic cohort, two-proportion z-test, CI on the lift. */
export function ABTestPanel() {
  const [tier, setTier] = useState(3);
  const [device, setDevice] = useState("Android_budget");
  const [category, setCategory] = useState("fashion");
  const [listPrice, setListPrice] = useState(4999);
  const [sampleSize, setSampleSize] = useState(4000);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<AbTestResult | null>(null);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await runAbTest({
        segment: {
          city_tier: tier,
          device_type: device,
          product_category: category,
          list_price: listPrice,
        },
        sample_size: sampleSize,
      });
      setRes(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-800">
          A/B test simulator
          <span className="ml-2 font-normal text-zinc-400">
            control (flat) vs friction-aware treatment
          </span>
        </h2>
        {res && (
          <span className="text-[11px] text-zinc-400">
            {res.sample_size.toLocaleString()} shoppers · {res.elapsed_ms} ms
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Field label="City tier">
          <select
            className="w-full rounded border border-zinc-200 px-2 py-1 text-xs"
            value={tier}
            onChange={(e) => setTier(Number(e.target.value))}
          >
            {[1, 2, 3].map((t) => (
              <option key={t} value={t}>
                Tier {t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Device">
          <select
            className="w-full rounded border border-zinc-200 px-2 py-1 text-xs"
            value={device}
            onChange={(e) => setDevice(e.target.value)}
          >
            {DEVICES.map((d) => (
              <option key={d} value={d}>
                {d.replace("_", " ")}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Category">
          <select
            className="w-full rounded border border-zinc-200 px-2 py-1 text-xs"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </Field>
        <Field label="List price ₹">
          <input
            type="number"
            className="w-full rounded border border-zinc-200 px-2 py-1 text-xs"
            value={listPrice}
            min={99}
            onChange={(e) => setListPrice(Number(e.target.value) || 0)}
          />
        </Field>
        <Field label={`Sample ${sampleSize.toLocaleString()}`}>
          <input
            type="range"
            min={500}
            max={12000}
            step={500}
            className="w-full accent-brand"
            value={sampleSize}
            onChange={(e) => setSampleSize(Number(e.target.value))}
          />
        </Field>
      </div>

      <button
        onClick={run}
        disabled={busy}
        className="mt-4 rounded bg-brand px-4 py-1.5 text-xs font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
      >
        {busy ? "Simulating…" : "Run experiment"}
      </button>

      {err && <p className="mt-3 text-xs text-red-600">{err}</p>}

      {res && <Results res={res} />}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] uppercase tracking-wide text-zinc-400">
        {label}
      </span>
      {children}
    </label>
  );
}

function Results({ res }: { res: AbTestResult }) {
  const { control, treatment } = res.arms;
  const sig = res.significance;
  const lift = res.lift;
  const convData = [
    { arm: "Control", pct: +(control.conversion_rate * 100).toFixed(2), fill: "#a1a1aa" },
    { arm: "Treatment", pct: +(treatment.conversion_rate * 100).toFixed(2), fill: "#4f46e5" },
  ];
  const rpvData = [
    { arm: "Control", v: +control.rpv.toFixed(0), fill: "#a1a1aa" },
    { arm: "Treatment", v: +treatment.rpv.toFixed(0), fill: "#4f46e5" },
  ];

  return (
    <div className="mt-5 space-y-5">
      {/* verdict banner */}
      <div
        className={`rounded-lg border p-3 text-xs ${
          sig.significant
            ? lift.rpv_abs >= 0
              ? "border-emerald-200 bg-emerald-50 text-emerald-900"
              : "border-amber-200 bg-amber-50 text-amber-900"
            : "border-zinc-200 bg-zinc-50 text-zinc-600"
        }`}
      >
        <p className="font-semibold">
          {sig.significant
            ? `Statistically significant (p = ${fmtP(sig.p_value)})`
            : `Not significant (p = ${fmtP(sig.p_value)}) — widen the sample or the effect is marginal`}
        </p>
        <p className="mt-1">
          Revenue / visitor{" "}
          <strong>
            {lift.rpv_abs >= 0 ? "+" : ""}
            {inr(lift.rpv_abs)}
          </strong>{" "}
          ({lift.rpv_rel_pct >= 0 ? "+" : ""}
          {lift.rpv_rel_pct.toFixed(1)}%) · conversion{" "}
          <strong>
            {lift.conversion_rate_abs >= 0 ? "+" : ""}
            {(lift.conversion_rate_abs * 100).toFixed(2)} pts
          </strong>{" "}
          · 95% CI on conversion lift [
          {(sig.ci95_conversion_lift[0] * 100).toFixed(2)},{" "}
          {(sig.ci95_conversion_lift[1] * 100).toFixed(2)}] pts
        </p>
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-[11px] text-zinc-500">Conversion rate</p>
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={convData} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="arm" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} width={38} />
              <Bar dataKey="pct" radius={[3, 3, 0, 0]}>
                <LabelList dataKey="pct" position="top" formatter={(v: number) => `${v}%`} style={{ fontSize: 11 }} />
                {convData.map((d, i) => (
                  <Cell key={i} fill={d.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <p className="mb-1 text-[11px] text-zinc-500">Revenue per visitor</p>
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={rpvData} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="arm" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `₹${v}`} width={48} />
              <Bar dataKey="v" radius={[3, 3, 0, 0]}>
                <LabelList dataKey="v" position="top" formatter={(v: number) => `₹${v}`} style={{ fontSize: 11 }} />
                {rpvData.map((d, i) => (
                  <Cell key={i} fill={d.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid gap-4 text-xs sm:grid-cols-2">
        <div className="rounded-lg bg-zinc-50 p-3">
          <p className="text-zinc-500">Arms</p>
          <table className="mt-1 w-full">
            <tbody className="[&_td]:py-0.5">
              <tr className="text-zinc-400">
                <td />
                <td className="text-right">Control</td>
                <td className="text-right">Treatment</td>
              </tr>
              <Row k="Shoppers" c={control.n} t={treatment.n} />
              <Row k="Conversions" c={control.conversions} t={treatment.conversions} />
              <Row
                k="Conv. rate"
                c={`${(control.conversion_rate * 100).toFixed(2)}%`}
                t={`${(treatment.conversion_rate * 100).toFixed(2)}%`}
              />
              <Row k="Avg price" c={inr(control.avg_price)} t={inr(treatment.avg_price)} />
              <Row
                k="Markup share"
                c="—"
                t={`${((treatment.markup_share ?? 0) * 100).toFixed(0)}%`}
              />
            </tbody>
          </table>
        </div>

        <div className="rounded-lg bg-zinc-50 p-3">
          <p className="text-zinc-500">Which intervention did the work</p>
          {res.top_intervention ? (
            <p className="mt-1">
              <strong>{res.top_intervention.id.replace(/_/g, " ")}</strong> served to{" "}
              {(res.top_intervention.share_of_treatment * 100).toFixed(0)}% of the
              treatment arm{" "}
              {res.top_intervention.expected_conversion_lift &&
                `· lib. lift ${res.top_intervention.expected_conversion_lift}`}
            </p>
          ) : (
            <p className="mt-1 text-zinc-400">n/a</p>
          )}
          <p className="mt-2 text-zinc-500">Friction mix (treatment)</p>
          <ul className="mt-1 space-y-0.5">
            {res.friction_mix.slice(0, 4).map((f) => (
              <li key={f.type} className="flex items-center gap-2">
                <span className="w-28 shrink-0">{FRICTION_LABEL[f.type] ?? f.type}</span>
                <span className="h-1.5 flex-1 rounded bg-zinc-200">
                  <span
                    className="block h-full rounded bg-brand"
                    style={{ width: `${f.share * 100}%` }}
                  />
                </span>
                <span className="w-9 text-right text-zinc-400">
                  {(f.share * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="text-[10px] leading-relaxed text-zinc-400">{res.note}</p>
    </div>
  );
}

function Row({ k, c, t }: { k: string; c: React.ReactNode; t: React.ReactNode }) {
  return (
    <tr>
      <td className="text-zinc-500">{k}</td>
      <td className="text-right tabular-nums">{c}</td>
      <td className="text-right font-medium tabular-nums text-zinc-800">{t}</td>
    </tr>
  );
}

function fmtP(p: number): string {
  if (p < 1e-4) return "<0.0001";
  return p.toFixed(4);
}
