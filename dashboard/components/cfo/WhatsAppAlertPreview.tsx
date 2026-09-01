"use client";

import { useEffect, useState } from "react";
import { getOracleAlertPreview, shortDate } from "@/lib/cfoApi";
import type { AlertPreview } from "@/lib/cfoTypes";
import { Skeleton } from "./Skeleton";

const URGENCY: Record<string, { ring: string; dot: string; label: string }> = {
  high: { ring: "border-red-400", dot: "bg-red-500", label: "High urgency" },
  medium: { ring: "border-amber-400", dot: "bg-amber-500", label: "Medium urgency" },
  low: { ring: "border-emerald-400", dot: "bg-emerald-500", label: "All clear" },
};

export function WhatsAppAlertPreview({ merchantId }: { merchantId: string }) {
  const [a, setA] = useState<AlertPreview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setA(null);
    getOracleAlertPreview(merchantId)
      .then((r) => alive && setA(r))
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [merchantId]);

  const u = a ? URGENCY[a.urgency] : URGENCY.low;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-800">
          Proactive alert preview
        </h2>
        {a && (
          <span className="flex items-center gap-1.5 text-[10px] text-zinc-500">
            <span className={`h-2 w-2 rounded-full ${u.dot}`} />
            {u.label}
          </span>
        )}
      </div>

      {loading || !a ? (
        <Skeleton className="mx-auto h-64 w-64" />
      ) : (
        <div className="mx-auto max-w-[280px]">
          {/* phone frame */}
          <div
            className={`rounded-[28px] border-4 ${u.ring} bg-[#0b141a] p-2 shadow-xl`}
          >
            <div className="rounded-[20px] bg-[#0b141a] pb-3">
              <div className="flex items-center gap-2 rounded-t-[18px] bg-[#1f2c34] px-3 py-2 text-white">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand text-xs font-bold">
                  R
                </div>
                <div className="leading-tight">
                  <p className="text-[11px] font-semibold">{a.sender}</p>
                  <p className="text-[9px] text-emerald-300">online</p>
                </div>
              </div>
              <div
                className="space-y-1 px-3 py-3"
                style={{
                  backgroundImage:
                    "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16'%3E%3Ccircle cx='2' cy='2' r='1' fill='%23223'/%3E%3C/svg%3E\")",
                }}
              >
                <div className="ml-auto max-w-[92%] rounded-lg rounded-tr-none bg-[#005c4b] px-2.5 py-2 text-[11px] leading-snug text-white shadow">
                  <p className="mb-1 font-semibold">{a.title}</p>
                  <p className="whitespace-pre-wrap text-white/90">{a.body}</p>
                  {a.apply_by_date && (
                    <p className="mt-1 text-[10px] text-emerald-200">
                      Apply by {shortDate(a.apply_by_date)}
                    </p>
                  )}
                  <button className="mt-2 w-full rounded bg-white/15 py-1 text-[10px] font-semibold">
                    {a.recommended_action.startsWith("No")
                      ? "View forecast"
                      : "Tap to apply →"}
                  </button>
                  <p className="mt-0.5 text-right text-[8px] text-white/50">
                    now ✓✓
                  </p>
                </div>
              </div>
            </div>
          </div>
          <p className="mt-2 text-center text-[10px] text-zinc-400">
            Mockup — no message is sent. Recommended action: {a.recommended_action}
          </p>
        </div>
      )}
    </section>
  );
}
