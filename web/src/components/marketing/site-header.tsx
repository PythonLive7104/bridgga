import Link from "next/link";

import { WordmarkLink } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";

/**
 * Minimal header: wordmark, a short nav, one primary action.
 *
 * No mega-menu. The breadth of the product (PRD section 11 lists dozens of
 * routes) belongs in the footer, where it is crawlable without pushing the
 * hero below the fold.
 */
const NAV = [
  { href: "/product", label: "Product" },
  { href: "/customers", label: "Customers" },
  { href: "/pricing", label: "Pricing" },
  { href: "/resources", label: "Resources" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-bg/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4">
        <WordmarkLink height={30} priority />

        <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-2 text-sm text-fg-muted transition-colors hover:bg-bg-subtle hover:text-fg"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link
            href="/auth/login"
            className="hidden rounded-md px-3 py-2 text-sm text-fg-muted transition-colors hover:text-fg sm:block"
          >
            Sign in
          </Link>
          <Link
            href="/auth/signup"
            className="inline-flex h-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-accent px-4 text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >
            Find my customers
          </Link>
        </div>
      </div>
    </header>
  );
}
