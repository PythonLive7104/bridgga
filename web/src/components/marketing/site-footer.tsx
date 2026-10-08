import Link from "next/link";

/**
 * Multi-column footer.
 *
 * This is where the long tail of PRD section 11 lives: features, industries,
 * use cases and country pages, all reachable as crawlable HTML links rather
 * than hidden behind a JS menu (PRD section 19).
 */
const COLUMNS: { heading: string; links: { href: string; label: string }[] }[] = [
  {
    heading: "Product",
    links: [
      { href: "/features/ai-prospecting", label: "AI prospecting" },
      { href: "/features/buying-signals", label: "Buying signals" },
      { href: "/features/company-intelligence", label: "Company intelligence" },
      { href: "/features/ai-sales-agent", label: "AI sales agent" },
      { href: "/features/crm", label: "CRM & pipeline" },
      { href: "/features/revenue-attribution", label: "Revenue attribution" },
    ],
  },
  {
    heading: "Channels",
    links: [
      { href: "/features/email-outreach", label: "Email outreach" },
      { href: "/features/whatsapp-sales", label: "WhatsApp sales" },
      { href: "/features/linkedin-prospecting", label: "LinkedIn prospecting" },
      { href: "/features/website-analysis", label: "Website analysis" },
      { href: "/features/lead-scoring", label: "Lead scoring" },
    ],
  },
  {
    heading: "Markets",
    links: [
      { href: "/countries/nigeria", label: "Nigeria" },
      { href: "/countries/kenya", label: "Kenya" },
      { href: "/countries/ghana", label: "Ghana" },
      { href: "/countries/south-africa", label: "South Africa" },
      { href: "/countries/egypt", label: "Egypt" },
      { href: "/countries", label: "All markets" },
    ],
  },
  {
    heading: "Use cases",
    links: [
      { href: "/use-cases/get-first-customers", label: "Get first customers" },
      { href: "/use-cases/saas-outbound", label: "SaaS outbound" },
      { href: "/use-cases/agency-client-acquisition", label: "Agency growth" },
      { href: "/use-cases/international-market-entry", label: "Market entry" },
      { href: "/tools", label: "Free tools" },
    ],
  },
  {
    heading: "Company",
    links: [
      { href: "/about", label: "About" },
      { href: "/customers", label: "Case studies" },
      { href: "/blog", label: "Blog" },
      { href: "/research", label: "Research" },
      { href: "/developers", label: "Developers" },
      { href: "/contact", label: "Contact" },
    ],
  },
  {
    heading: "Trust",
    links: [
      { href: "/security", label: "Security" },
      { href: "/trust", label: "Trust center" },
      { href: "/status", label: "Status" },
      { href: "/privacy", label: "Privacy" },
      { href: "/terms", label: "Terms" },
      { href: "/acceptable-use", label: "Acceptable use" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-bg-subtle">
      <div className="mx-auto max-w-6xl px-4 py-14">
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-3 lg:grid-cols-6">
          {COLUMNS.map((column) => (
            <nav key={column.heading} aria-label={column.heading}>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-subtle">
                {column.heading}
              </h2>
              <ul className="space-y-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-fg-muted transition-colors hover:text-fg"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-4 border-t border-border pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-fg-subtle">
            &copy; {new Date().getFullYear()} Palatial. Built for African businesses.
            Ready for the world.
          </p>
          <p className="text-sm text-fg-subtle">
            Compliant outreach only. We do not sell scraped personal data.
          </p>
        </div>
      </div>
    </footer>
  );
}
