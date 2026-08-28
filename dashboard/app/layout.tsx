import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WTP Dynamic Pricing Engine - Live Demo",
  description:
    "Real-time willingness-to-pay estimation and checkout personalisation for Indian ecommerce. Razorpay AI Buildathon 2026, Track 01.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
              <div>
                <h1 className="text-lg font-semibold text-ink">
                  WTP Dynamic Pricing Engine
                </h1>
                <p className="text-xs text-slate-500">
                  Willingness-to-pay estimation · checkout personalisation ·
                  &lt;200&nbsp;ms · Razorpay AI Buildathon 2026 · Track 01
                </p>
              </div>
              <span className="rounded-full bg-brand/10 px-3 py-1 text-xs font-medium text-brand-dark">
                live demo
              </span>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
          <footer className="mx-auto max-w-7xl px-6 pb-10 pt-4 text-xs text-slate-400">
            Prices shown are model output on synthetic data. See{" "}
            <code>/docs/ARCHITECTURE.md</code> for the ethical framing:
            segment-level pricing, hard ±caps, never worse than list for
            low-trust shoppers.
          </footer>
        </div>
      </body>
    </html>
  );
}
