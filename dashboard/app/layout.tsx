import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "WTP Dynamic Pricing Engine",
  description:
    "Real-time willingness-to-pay estimation and checkout personalisation for Indian ecommerce. Razorpay AI Buildathon 2026.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3.5">
              <Link href="/dashboard" className="flex flex-col">
                <span className="text-sm font-semibold text-ink">
                  WTP Dynamic Pricing Engine
                </span>
                <span className="text-[11px] text-slate-500">
                  willingness-to-pay pricing · &lt;200&nbsp;ms · Razorpay AI
                  Buildathon 2026
                </span>
              </Link>
              <nav className="flex items-center gap-3 text-xs">
                <Link
                  href="/dashboard"
                  className="rounded px-2 py-1 font-medium text-slate-600 hover:bg-slate-100"
                >
                  Seller dashboard
                </Link>
                <span className="rounded-full bg-brand/10 px-3 py-1 font-medium text-brand-dark">
                  live demo
                </span>
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
          <footer className="mx-auto max-w-7xl px-6 pb-10 pt-4 text-xs text-slate-400">
            Prices are model output on synthetic data. Segment-level pricing with
            hard ±caps — a price-sensitive shopper is never charged more than
            list. See <code>docs/ARCHITECTURE.md</code>.
          </footer>
        </div>
      </body>
    </html>
  );
}
