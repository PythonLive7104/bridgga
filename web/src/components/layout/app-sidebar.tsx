"use client";

import {
  BarChart3,
  Bot,
  Building2,
  CalendarCheck,
  CreditCard,
  Inbox,
  LayoutDashboard,
  LineChart,
  Plug,
  Radar,
  Settings,
  Sparkles,
  Target,
  Trophy,
  Users,
  Wallet,
} from "lucide-react";
import Link from "next/link";

import { WordmarkLink } from "@/components/brand";
import { usePathname } from "next/navigation";
import * as React from "react";

import { useSession } from "@/lib/hooks/use-session";
import { cn } from "@/lib/utils";

/**
 * Sidebar structure is PRD section 115, verbatim in grouping and order.
 *
 * `capability` hides an item the current role cannot use. That is presentation
 * only -- the server authorises every request independently, so a hidden link
 * is a tidier UI, never a security boundary.
 */
interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  capability?: string;
}

interface NavGroup {
  heading: string | null;
  items: NavItem[];
}

const NAV: NavGroup[] = [
  {
    heading: null,
    items: [{ href: "/dashboard", label: "Overview", icon: LayoutDashboard }],
  },
  {
    heading: "Find Customers",
    items: [
      {
        href: "/company-profile",
        label: "Your company",
        icon: Building2,
        capability: "company_profile.view",
      },
      {
        href: "/prospects",
        label: "Prospects",
        icon: Target,
        capability: "prospect.view",
      },
      {
        href: "/companies",
        label: "Companies",
        icon: Building2,
        capability: "prospect.view",
      },
      { href: "/signals", label: "Signals", icon: Radar, capability: "prospect.view" },
      { href: "/icp", label: "ICP", icon: Sparkles, capability: "prospect.view" },
    ],
  },
  {
    heading: "Engage",
    items: [
      {
        href: "/campaigns",
        label: "Campaigns",
        icon: Sparkles,
        capability: "campaign.view",
      },
      { href: "/inbox", label: "Inbox", icon: Inbox, capability: "conversation.view" },
      { href: "/agent", label: "AI Sales Agent", icon: Bot, capability: "campaign.view" },
    ],
  },
  {
    heading: "Sell",
    items: [
      {
        href: "/pipeline",
        label: "Pipeline",
        icon: BarChart3,
        capability: "pipeline.view",
      },
      {
        href: "/meetings",
        label: "Meetings",
        icon: CalendarCheck,
        capability: "pipeline.view",
      },
      {
        href: "/opportunities",
        label: "Opportunities",
        icon: Trophy,
        capability: "pipeline.view",
      },
      {
        href: "/customers",
        label: "Customers",
        icon: Users,
        capability: "pipeline.view",
      },
    ],
  },
  {
    heading: "Analyze",
    items: [
      {
        href: "/analytics",
        label: "Analytics",
        icon: LineChart,
        capability: "analytics.view",
      },
      { href: "/revenue", label: "Revenue", icon: Wallet, capability: "analytics.view" },
      { href: "/advisor", label: "AI Advisor", icon: Bot, capability: "analytics.view" },
    ],
  },
  {
    heading: null,
    items: [
      {
        href: "/integrations",
        label: "Integrations",
        icon: Plug,
        capability: "integration.manage",
      },
      {
        href: "/billing",
        label: "Billing",
        icon: CreditCard,
        capability: "billing.view",
      },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { can, isLoading } = useSession();

  return (
    <nav
      aria-label="Main"
      className="flex h-full w-60 shrink-0 flex-col gap-5 overflow-y-auto border-r border-border bg-bg-subtle px-3 py-4"
    >
      <WordmarkLink href="/dashboard" height={26} className="px-2" />

      {NAV.map((group, groupIndex) => {
        // While the session loads, show everything rather than flashing a
        // collapsed menu that then expands.
        const items = isLoading
          ? group.items
          : group.items.filter((item) => !item.capability || can(item.capability));
        if (items.length === 0) return null;

        return (
          <div
            key={group.heading ?? `group-${groupIndex}`}
            className="flex flex-col gap-1"
          >
            {group.heading ? (
              <h2 className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">
                {group.heading}
              </h2>
            ) : null}

            {items.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2.5 rounded-[var(--radius-control)] px-2 py-2 text-sm transition-colors",
                    active
                      ? "bg-accent-subtle font-medium text-accent"
                      : "text-fg-muted hover:bg-surface hover:text-fg",
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}
