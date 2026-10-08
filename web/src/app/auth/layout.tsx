import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { WordmarkLink } from "@/components/brand";

/**
 * Split layout: what the product does on one side, the form on the other.
 *
 * The left panel is not decoration. Someone arriving at a signup form from a
 * search result or a shared link may have no idea what this is, and a bare
 * form gives them nothing to decide with. It is hidden below `lg` rather than
 * stacked, because on a phone it would push the form off the screen -- the one
 * thing the page exists to show.
 *
 * Its claims are deliberately about what the product *does*, not how well it
 * performs. PRD section 88 permits verified metrics only, and there is nothing
 * yet to verify.
 */

const PROOF = [
  { figure: "10", label: "African markets, each with its own channel mix" },
  { figure: "Every claim", label: "carries its source and the date we read it" },
  { figure: "Campaign → revenue", label: "joined up, not guessed at" },
];

export default function AuthLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-dvh flex-col lg:grid lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-bg-subtle px-12 py-10 lg:flex lg:flex-col">
        {/* Texture only: aria-hidden so it is not described, and
            pointer-events-none so it can never swallow a click. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "linear-gradient(to right, var(--border) 1px, transparent 1px), linear-gradient(to bottom, var(--border) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage: "radial-gradient(ellipse 80% 60% at 30% 40%, black, transparent)",
            WebkitMaskImage:
              "radial-gradient(ellipse 80% 60% at 30% 40%, black, transparent)",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -left-32 top-1/4 size-[32rem] rounded-full bg-accent/10 blur-3xl"
        />

        <div className="relative">
          <WordmarkLink height={30} priority />
        </div>

        <div className="relative my-auto max-w-lg py-10">
          <h2 className="text-balance text-4xl font-semibold leading-tight tracking-tight text-fg">
            Turn your website into a customer acquisition engine.
          </h2>
          <p className="mt-4 text-pretty text-base leading-relaxed text-fg-muted">
            We read what you sell, work out who needs it, find those companies in your
            markets, and tell you why each one is worth a conversation today.
          </p>

          <dl className="mt-10 grid gap-6 sm:grid-cols-3">
            {PROOF.map((item) => (
              <div key={item.label}>
                <dt className="text-lg font-semibold tracking-tight text-fg">
                  {item.figure}
                </dt>
                <dd className="mt-1 text-sm leading-snug text-fg-subtle">{item.label}</dd>
              </div>
            ))}
          </dl>
        </div>

        <p className="relative text-xs text-fg-subtle">
          &copy; {new Date().getFullYear()} Bridgga. Compliant outreach only.
        </p>
      </aside>

      <div className="flex flex-1 flex-col">
        {/* Repeated for the narrow layout, where the panel is hidden and the
            form would otherwise carry no branding at all. */}
        <header className="px-6 py-6 lg:hidden">
          <WordmarkLink height={28} priority />
        </header>

        <main
          id="main"
          className="flex flex-1 items-center justify-center px-6 pb-10 lg:px-12 lg:py-12"
        >
          <div className="w-full max-w-md">{children}</div>
        </main>

        <footer className="px-6 pb-8 text-center lg:px-12">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-fg-subtle transition-colors hover:text-fg"
          >
            <ArrowLeft aria-hidden className="size-3.5" />
            Back to home
          </Link>
        </footer>
      </div>
    </div>
  );
}
