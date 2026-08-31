"use client";

import Link from "next/link";
import { ABTestPanel } from "@/components/ABTestPanel";
import { ConversionFunnel } from "@/components/ConversionFunnel";
import { InterventionPerformance } from "@/components/InterventionPerformance";

function Label({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
      {children}
    </h2>
  );
}

/** Merchant analytics hub for the friction-aware conversion engine:
 *  the A/B test simulator (Step 4) and the conversion funnel (Step 5). */
export default function MerchantDashboardPage() {
  return (
    <div className="space-y-7">
      <div className="flex items-baseline justify-between">
        <h1 className="text-base font-semibold text-ink">Conversion analytics</h1>
        <Link href="/dashboard" className="text-xs text-brand hover:underline">
          ← Seller dashboard
        </Link>
      </div>

      <section>
        <Label>Conversion funnel</Label>
        <ConversionFunnel />
      </section>

      <section>
        <Label>Intervention performance</Label>
        <InterventionPerformance />
      </section>

      <section>
        <Label>Friction-aware A/B test</Label>
        <ABTestPanel />
      </section>
    </div>
  );
}
