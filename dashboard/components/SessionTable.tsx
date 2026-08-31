"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getAllSessions } from "@/lib/api";
import { PRESET_LABELS, inr } from "@/lib/profiles";
import { useSessionsFeed } from "@/lib/ws";
import type { Preset, SessionInfo } from "@/lib/types";

const STATUS: Record<string, string> = {
  pending: "text-zinc-500 bg-zinc-100",
  priced: "text-brand-dark bg-brand/10",
  converted: "text-emerald-700 bg-emerald-100",
  abandoned: "text-amber-700 bg-amber-100",
};

function ago(iso?: string): string {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

const FRICTION_SHORT: Record<string, string> = {
  price_sensitivity: "price-sensitive",
  trust_deficit: "trust deficit",
  decision_paralysis: "paralysis",
  payment_friction: "payment friction",
  delivery_anxiety: "delivery anxiety",
  urgency_insensitive: "urgency-insensitive",
};

function outcome(status: string): { label: string; cls: string } {
  if (status === "converted") return { label: "converted ✓", cls: "text-emerald-700" };
  if (status === "abandoned") return { label: "abandoned ✗", cls: "text-amber-700" };
  if (status === "priced") return { label: "in progress", cls: "text-zinc-400" };
  return { label: "—", cls: "text-zinc-300" };
}

export function SessionTable({ refreshSignal }: { refreshSignal?: number }) {
  const [seed, setSeed] = useState<SessionInfo[]>([]);
  const [backend, setBackend] = useState<string>("");
  const { sessions, connected } = useSessionsFeed(seed);

  useEffect(() => {
    let alive = true;
    getAllSessions()
      .then((r) => {
        if (!alive) return;
        setSeed(r.sessions);
        setBackend(r.backend);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [refreshSignal]);

  return (
    <div className="rounded-lg border border-zinc-200 bg-white shadow-card">
      <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-2">
        <span className="text-xs text-zinc-400">
          {sessions.length} session{sessions.length === 1 ? "" : "s"}
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-zinc-400">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              connected ? "bg-emerald-500" : "bg-amber-400"
            }`}
          />
          {connected ? "live · websocket" : "polling"} · {backend || "…"}
        </span>
      </div>

      <div className="max-h-[340px] overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-white text-[10px] uppercase tracking-wider text-zinc-400">
            <tr className="border-b border-zinc-100">
              <th className="px-4 py-2 font-medium">Session</th>
              <th className="px-4 py-2 font-medium">Profile</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Friction · fix</th>
              <th className="px-4 py-2 text-right font-medium">Exp. lift</th>
              <th className="px-4 py-2 font-medium">Outcome</th>
              <th className="px-4 py-2 text-right font-medium">WTP</th>
              <th className="px-4 py-2 text-right font-medium">Price</th>
              <th className="px-4 py-2 text-right font-medium">Age</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {sessions.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-6 text-center text-zinc-400">
                  No sessions yet.
                </td>
              </tr>
            )}
            {sessions.map((s) => (
              <tr key={s.session_id} className="border-b border-zinc-50 hover:bg-zinc-50/60">
                <td className="px-4 py-1.5 font-mono text-[10px] text-zinc-400">
                  {s.session_id.replace("sess_", "").slice(0, 10)}
                </td>
                <td className="px-4 py-1.5">
                  <span className="text-zinc-700">
                    {PRESET_LABELS[s.preset as Preset]?.label ?? s.preset}
                  </span>
                  <span className="ml-1 text-zinc-400">
                    T{s.config?.city_tier}·{(s.config?.device_type ?? "").replace("Android_", "A_")}
                  </span>
                </td>
                <td className="px-4 py-1.5">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      STATUS[s.status] ?? STATUS.pending
                    }`}
                  >
                    {s.status}
                  </span>
                </td>
                <td className="px-4 py-1.5">
                  {s.result?.checkout_config ? (
                    <span className="text-zinc-600">
                      {FRICTION_SHORT[s.result.checkout_config.friction_type] ??
                        s.result.checkout_config.friction_type}
                      <span className="ml-1 text-zinc-400">
                        →{" "}
                        {s.result.checkout_config.primary_intervention.replace(
                          /_/g,
                          " ",
                        )}
                      </span>
                    </span>
                  ) : (
                    <span className="text-zinc-300">—</span>
                  )}
                </td>
                <td className="px-4 py-1.5 text-right tabular-nums text-zinc-500">
                  {s.result?.checkout_config?.expected_conversion_lift ?? "—"}
                </td>
                <td className={`px-4 py-1.5 text-[11px] ${outcome(s.status).cls}`}>
                  {outcome(s.status).label}
                </td>
                <td className="px-4 py-1.5 text-right tabular-nums text-zinc-600">
                  {s.wtp_score != null ? `×${s.wtp_score.toFixed(3)}` : "—"}
                </td>
                <td className="px-4 py-1.5 text-right tabular-nums font-medium text-ink">
                  {inr(s.price_shown)}
                </td>
                <td className="px-4 py-1.5 text-right text-zinc-400">{ago(s.created_at)}</td>
                <td className="px-4 py-1.5 text-right">
                  <Link
                    href={`/merchant/${s.session_id}`}
                    className="text-[10px] font-medium text-brand-dark hover:underline"
                  >
                    view →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
