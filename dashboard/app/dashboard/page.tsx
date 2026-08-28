"use client";

import { useCallback, useState } from "react";
import { LinkGenerator } from "@/components/LinkGenerator";
import { SessionTable } from "@/components/SessionTable";
import { MetricsPanel } from "@/components/MetricsPanel";
import { SegmentExplorer } from "@/components/SegmentExplorer";
import type { SessionCreateResponse } from "@/lib/types";

export default function DashboardPage() {
  const [refresh, setRefresh] = useState(0);
  const [lastCreated, setLastCreated] = useState<SessionCreateResponse | null>(null);

  const onCreated = useCallback((s: SessionCreateResponse) => {
    setLastCreated(s);
    setRefresh((r) => r + 1);
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-lg font-semibold text-ink">Seller Dashboard</h1>
        <p className="text-xs text-slate-500">
          Generate a personalised checkout link for any customer profile, then
          watch the pricing decision land live.
        </p>
      </div>

      <LinkGenerator onCreated={onCreated} />

      <SessionTable refreshSignal={refresh} />

      {/* existing aggregate analytics - unchanged */}
      <div>
        <h2 className="mb-2 text-sm font-semibold text-ink">Aggregate analytics</h2>
        <MetricsPanel refreshKey={refresh} />
      </div>

      {/* segment confidence intervals */}
      <SegmentExplorer seedSegment={lastCreated?.segment_key} />
    </div>
  );
}
