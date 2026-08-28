"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getAllSessions } from "@/lib/api";
import { PRESET_LABELS, STATUS_STYLE, inr } from "@/lib/profiles";
import { useSessionsFeed } from "@/lib/ws";
import type { Preset, SessionInfo } from "@/lib/types";

function ago(iso?: string): string {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
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
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <h2 className="text-sm font-semibold text-ink">
          Live sessions{" "}
          <span className="font-normal text-slate-400">({sessions.length})</span>
        </h2>
        <span className="flex items-center gap-1.5 text-[10px] text-slate-400">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              connected ? "bg-emerald-500" : "bg-slate-300"
            }`}
          />
          {connected ? "live" : "reconnecting"} · {backend || "…"}
        </span>
      </div>

      <div className="max-h-[360px] overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-2 font-medium">Session</th>
              <th className="px-4 py-2 font-medium">Profile</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">WTP</th>
              <th className="px-4 py-2 font-medium">Price shown</th>
              <th className="px-4 py-2 font-medium">Created</th>
              <th className="px-4 py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {sessions.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-slate-400">
                  No sessions yet — generate a link above.
                </td>
              </tr>
            )}
            {sessions.map((s) => {
              const st = STATUS_STYLE[s.status] ?? STATUS_STYLE.pending;
              return (
                <tr key={s.session_id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-2 font-mono text-[10px] text-slate-500">
                    {s.session_id.replace("sess_", "").slice(0, 10)}
                  </td>
                  <td className="px-4 py-2">
                    <span className="font-medium text-slate-700">
                      {PRESET_LABELS[s.preset as Preset]?.label ?? s.preset}
                    </span>
                    <span className="ml-1 text-slate-400">
                      T{s.config?.city_tier}·{s.config?.device_type?.replace("Android_", "A_")}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${st.cls}`}>
                      {st.label}
                    </span>
                  </td>
                  <td className="px-4 py-2 tabular-nums text-slate-600">
                    {s.wtp_score != null ? `×${s.wtp_score.toFixed(3)}` : "—"}
                  </td>
                  <td className="px-4 py-2 tabular-nums font-medium text-ink">
                    {inr(s.price_shown)}
                    {s.offer_type && s.offer_type !== "none" && (
                      <span className="ml-1 text-[10px] font-normal text-slate-400">
                        + {s.offer_type}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-slate-400">{ago(s.created_at)}</td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      href={`/merchant/${s.session_id}`}
                      className="rounded border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-brand-dark hover:bg-slate-50"
                    >
                      merchant view
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
