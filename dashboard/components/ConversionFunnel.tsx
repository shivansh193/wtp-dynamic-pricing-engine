"use client";

import { useEffect, useState } from "react";
import { getFunnel } from "@/lib/api";
import type { FunnelResult, FunnelStage } from "@/lib/types";

const FRICTION_COLOR: Record<string, string> = {
  price_sensitivity: "#4f46e5",
  trust_deficit: "#0891b2",
  decision_paralysis: "#7c3aed",
  payment_friction: "#db2777",
  delivery_anxiety: "#d97706",
  urgency_insensitive: "#059669",
  unknown: "#a1a1aa",
};
const FRICTION_LABEL: Record<string, string> = {
  price_sensitivity: "Price sensitivity",
  trust_deficit: "Trust deficit",
  decision_paralysis: "Decision paralysis",
  payment_friction: "Payment friction",
  delivery_anxiety: "Delivery anxiety",
  urgency_insensitive: "Urgency-insensitive",
  unknown: "Unclassified",
};

/** Four-stage checkout funnel with drop-off attributed to friction type.
 *  Backed by GET /funnel (decision log + synthetic fill). Click a stage to
 *  see the frictions and interventions at that leak. */
export function ConversionFunnel() {
  const [data, setData] = useState<FunnelResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>("payment_selected");

  const load = () => {
    setBusy(true);
    getFunnel()
      .then((d) => {
        setData(d);
        setErr(null);
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setBusy(false));
  };

  useEffect(load, []);

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-800">
          Conversion funnel
          <span className="ml-2 font-normal text-zinc-400">
            drop-off by friction type
          </span>
        </h2>
        <div className="flex items-center gap-3 text-[11px] text-zinc-400">
          {data && (
            <span>
              {data.n.toLocaleString()} shoppers ·{" "}
              <span
                className={
                  data.data_source === "decision_log"
                    ? "text-emerald-600"
                    : "text-amber-600"
                }
              >
                {data.data_source}
              </span>
            </span>
          )}
          <button onClick={load} disabled={busy} className="hover:text-zinc-600">
            {busy ? "…" : "↻"}
          </button>
        </div>
      </div>

      {err && <p className="text-xs text-red-600">{err}</p>}
      {!data ? (
        <p className="text-xs text-zinc-400">loading…</p>
      ) : (
        <>
          <p className="mb-3 text-xs text-zinc-500">
            Overall conversion{" "}
            <strong className="text-zinc-800">
              {(data.overall_conversion * 100).toFixed(1)}%
            </strong>
            {data.biggest_leak && (
              <>
                {" · biggest leak: "}
                <span className="font-medium text-amber-700">
                  {data.biggest_leak.label} (−
                  {data.biggest_leak.dropoff_pct_of_prev.toFixed(1)}%
                  {data.biggest_leak.leading_friction &&
                    `, mostly ${
                      FRICTION_LABEL[data.biggest_leak.leading_friction] ??
                      data.biggest_leak.leading_friction
                    }`}
                  )
                </span>
              </>
            )}
          </p>

          <div className="space-y-1.5">
            {data.stages.map((s, i) => (
              <StageRow
                key={s.stage}
                stage={s}
                prev={i > 0 ? data.stages[i - 1] : null}
                active={open === s.stage}
                onClick={() =>
                  i === 0 ? null : setOpen(open === s.stage ? null : s.stage)
                }
              />
            ))}
          </div>

          {open && <Detail stage={data.stages.find((s) => s.stage === open)} />}

          <p className="mt-4 text-[10px] leading-relaxed text-zinc-400">
            {data.note}
          </p>
        </>
      )}
    </section>
  );
}

function StageRow({
  stage,
  prev,
  active,
  onClick,
}: {
  stage: FunnelStage;
  prev: FunnelStage | null;
  active: boolean;
  onClick: () => void;
}) {
  const clickable = !!prev;
  return (
    <div>
      {prev && (
        <div className="flex items-center gap-2 py-0.5 pl-1 text-[10px] text-zinc-400">
          <span className="text-amber-600">
            ▼ −{stage.dropoff_pct_of_prev?.toFixed(1)}%
          </span>
          <span className="flex h-1.5 flex-1 overflow-hidden rounded bg-zinc-100">
            {(stage.dropoff_by_friction ?? []).map((f) => (
              <span
                key={f.key}
                title={`${FRICTION_LABEL[f.key] ?? f.key} ${(f.share * 100).toFixed(
                  0,
                )}%`}
                style={{
                  width: `${f.share * 100}%`,
                  background: FRICTION_COLOR[f.key] ?? "#a1a1aa",
                }}
              />
            ))}
          </span>
        </div>
      )}
      <button
        onClick={onClick}
        disabled={!clickable}
        className={`group flex w-full items-center gap-3 rounded px-1 py-1 text-left ${
          clickable ? "hover:bg-zinc-50" : "cursor-default"
        } ${active ? "bg-zinc-50" : ""}`}
      >
        <span className="w-40 shrink-0 text-xs text-zinc-600">{stage.label}</span>
        <span className="relative h-6 flex-1 rounded bg-zinc-100">
          <span
            className="absolute inset-y-0 left-0 rounded bg-brand/85"
            style={{ width: `${stage.reached_pct}%` }}
          />
          <span className="absolute inset-y-0 left-2 flex items-center text-[11px] font-medium text-white mix-blend-plus-lighter">
            {stage.reached_pct.toFixed(1)}%
          </span>
        </span>
        {clickable && (
          <span className="text-[10px] text-zinc-300 group-hover:text-zinc-500">
            {active ? "−" : "+"}
          </span>
        )}
      </button>
    </div>
  );
}

function Detail({ stage }: { stage?: FunnelStage }) {
  if (!stage || !stage.dropoff_by_friction) return null;
  return (
    <div className="mt-3 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs">
      <p className="font-semibold text-zinc-700">
        {stage.label} — {stage.dropoff?.toFixed(0)} shoppers lost (
        {stage.dropoff_pct_of_prev?.toFixed(1)}% of the previous stage)
      </p>
      {stage.explainer && (
        <p className="mt-1 text-zinc-500">{stage.explainer}</p>
      )}
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-[11px] text-zinc-500">Friction behind this drop</p>
          <ul className="space-y-1">
            {stage.dropoff_by_friction.map((f) => (
              <li key={f.key} className="flex items-center gap-2">
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: FRICTION_COLOR[f.key] ?? "#a1a1aa" }}
                />
                <span className="w-28 shrink-0">
                  {FRICTION_LABEL[f.key] ?? f.key}
                </span>
                <span className="h-1.5 flex-1 rounded bg-zinc-200">
                  <span
                    className="block h-full rounded"
                    style={{
                      width: `${f.share * 100}%`,
                      background: FRICTION_COLOR[f.key] ?? "#a1a1aa",
                    }}
                  />
                </span>
                <span className="w-9 text-right text-zinc-400">
                  {(f.share * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="mb-1 text-[11px] text-zinc-500">
            Interventions targeting it
          </p>
          <ul className="space-y-1">
            {(stage.top_interventions ?? []).map((iv) => (
              <li key={iv.key} className="flex justify-between">
                <span className="text-zinc-600">{iv.key.replace(/_/g, " ")}</span>
                <span className="text-zinc-400">
                  {(iv.share * 100).toFixed(0)}%
                </span>
              </li>
            ))}
            {!stage.top_interventions?.length && (
              <li className="text-zinc-400">—</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
