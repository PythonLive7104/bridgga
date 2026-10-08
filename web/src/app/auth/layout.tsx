import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { AuthPanel } from "@/components/auth/showcase";
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
 * What goes in it differs per route and lives in `AuthShowcase`; its claims
 * are deliberately about what the product *does*, not how well it performs,
 * because PRD section 88 permits verified metrics only and there is nothing
 * yet to verify.
 */

export default function AuthLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-dvh flex-col lg:grid lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-bg-subtle px-12 py-10 lg:flex lg:flex-col">
        <div className="relative">
          <WordmarkLink height={30} priority />
        </div>
        <AuthPanel />
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
