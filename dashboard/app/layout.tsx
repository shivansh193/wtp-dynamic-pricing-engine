import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "WTP Pricing Engine",
  description:
    "Willingness-to-pay pricing for Indian ecommerce checkouts. Razorpay AI Buildathon 2026.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-zinc-200 bg-white">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-2.5">
              <Link href="/dashboard" className="flex items-baseline gap-2">
                <span className="font-mono text-sm font-semibold tracking-tight text-ink">
                  wtp
                </span>
                <span className="text-[11px] text-zinc-400">
                  willingness-to-pay pricing
                </span>
              </Link>
              <div className="flex items-center gap-4 text-[11px] text-zinc-400">
                <span>Razorpay AI Buildathon 2026 · Track 01</span>
              </div>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
          <footer className="mx-auto max-w-7xl px-6 pb-10 pt-6 text-[11px] text-zinc-400">
            Prices are model output on synthetic data. Segment-level pricing
            inside a merchant-set band; a price-sensitive shopper is never
            charged more than list.
          </footer>
        </div>
      </body>
    </html>
  );
}
