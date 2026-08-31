"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { LinkGenerator } from "@/components/LinkGenerator";
import { MerchantSettings } from "@/components/MerchantSettings";
import { SessionTable } from "@/components/SessionTable";
import { MetricsPanel } from "@/components/MetricsPanel";
import { SegmentExplorer } from "@/components/SegmentExplorer";
import type { SessionCreateResponse } from "@/lib/types";

function Label({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
      {children}
    </h2>
  );
}

export default function DashboardPage() {
  const [refresh, setRefresh] = useState(0);
  const [lastCreated, setLastCreated] = useState<SessionCreateResponse | null>(null);

  const bump = useCallback(() => setRefresh((r) => r + 1), []);
  const onCreated = useCallback((s: SessionCreateResponse) => {
    setLastCreated(s);
    setRefresh((r) => r + 1);
  }, []);

  return (
    <div className="space-y-7">
      <div className="flex items-baseline justify-between">
        <h1 className="text-base font-semibold text-ink">Seller dashboard</h1>
        <div className="flex items-center gap-3 text-xs text-zinc-400">
          <Link href="/merchant/dashboard" className="text-brand hover:underline">
            Conversion analytics →
          </Link>
          <span>
            RunHub Official Store ·{" "}
            <span className="text-zinc-500">Nike Air Max</span>
          </span>
        </div>
      </div>

      <section>
        <Label>Generate a customer link</Label>
        <LinkGenerator onCreated={onCreated} />
      </section>

      <section>
        <Label>Live sessions</Label>
        <SessionTable refreshSignal={refresh} />
      </section>

      <section>
        <Label>Merchant controls</Label>
        <MerchantSettings onChange={bump} />
      </section>

      <section>
        <Label>Analytics</Label>
        <MetricsPanel refreshKey={refresh} />
      </section>

      <section>
        <Label>Segment confidence &amp; margin</Label>
        <SegmentExplorer seedSegment={lastCreated?.segment_key} />
      </section>
    </div>
  );
}
