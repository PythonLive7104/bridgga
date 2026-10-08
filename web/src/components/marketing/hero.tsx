import Link from "next/link";

import { ProspectTablePanel } from "@/components/marketing/panels";
import { Reveal } from "@/components/marketing/reveal";
import { Badge } from "@/components/ui/badge";

const MARKET_CHIPS = ["Nigeria", "Kenya", "Ghana", "South Africa", "Egypt", "+5 more"];

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* Decorative layers sit behind content and are hidden from assistive
          tech; the grid is masked so it fades out rather than ending abruptly. */}
      <div aria-hidden className="pointer-events-none absolute inset-0 gradient-wash" />
      <div aria-hidden className="pointer-events-none absolute inset-0 grid-texture" />

      <div className="relative mx-auto max-w-6xl px-4 pb-20 pt-20 sm:pt-28">
        <div className="mx-auto max-w-3xl text-center">
          <Badge tone="accent">AI Customer Acquisition OS</Badge>

          <h1 className="text-display mt-6 text-fg">
            Turn your website into a{" "}
            {/* The accent lands on the promise, not the whole headline. */}
            <span className="text-accent">customer acquisition engine</span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-fg-muted">
            AI finds the companies most likely to need your product, identifies the right
            decision makers, starts relevant conversations, and helps turn prospects into
            paying customers.
          </p>

          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/auth/signup"
              className="inline-flex h-12 w-full items-center justify-center rounded-[var(--radius-control)] bg-accent px-7 text-base font-medium text-accent-fg shadow-sm transition-colors hover:bg-accent-hover sm:w-auto"
            >
              Find my customers
            </Link>
            <Link
              href="#how-it-works"
              className="inline-flex h-12 w-full items-center justify-center rounded-[var(--radius-control)] border border-border bg-surface px-7 text-base font-medium text-fg transition-colors hover:border-border-strong sm:w-auto"
            >
              See how it works
            </Link>
          </div>

          <p className="mt-5 text-sm text-fg-subtle">
            Start free. No list to upload, no card required to see your first prospects.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-1.5">
            <span className="text-xs text-fg-subtle">Launch markets:</span>
            {MARKET_CHIPS.map((market) => (
              <Badge key={market}>{market}</Badge>
            ))}
          </div>
        </div>

        {/* Showing the actual ranked-prospect table this high up is the point:
            the product's claim is about deciding who deserves attention. */}
        <Reveal className="mt-16" delay={120}>
          <ProspectTablePanel />
        </Reveal>
      </div>
    </section>
  );
}
