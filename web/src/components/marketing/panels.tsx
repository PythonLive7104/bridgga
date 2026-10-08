import * as React from "react";

import { Badge, ScoreBadge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Product UI shown on the marketing page.
 *
 * Built from components, not screenshots: screenshots go stale the moment the
 * app changes, cannot be translated, and are invisible to crawlers and screen
 * readers.
 *
 * All company names here are fictional and the figures are illustrative. PRD
 * section 88 allows only verified metrics to be published as results, so
 * nothing on this page is presented as a customer outcome.
 */

/** Window chrome. Gives a flat panel the depth of a real screen. */
export function AppFrame({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface shadow-[var(--shadow-raised)]",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b border-border bg-bg-subtle px-4 py-2.5">
        <span aria-hidden className="flex gap-1.5">
          {["bg-signal-hot", "bg-signal-warm", "bg-positive"].map((dot) => (
            <span key={dot} className={cn("size-2.5 rounded-full opacity-60", dot)} />
          ))}
        </span>
        <span className="ml-1 truncate text-xs font-medium text-fg-subtle">{label}</span>
      </div>
      {children}
    </div>
  );
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <th
      scope="col"
      className={cn(
        "px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-fg-subtle",
        className,
      )}
    >
      {children}
    </th>
  );
}

function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={cn("px-4 py-3 align-middle text-sm", className)}>{children}</td>;
}

const PROSPECTS = [
  {
    company: "Harmattan Haulage",
    contact: "Ops Director",
    place: "Lagos, NG",
    industry: "Logistics",
    score: 91,
    signals: 3,
    status: "Ready",
  },
  {
    company: "Rift Valley Freight",
    contact: "Fleet Manager",
    place: "Nairobi, KE",
    industry: "Distribution",
    score: 84,
    signals: 2,
    status: "Ready",
  },
  {
    company: "Volta Distribution",
    contact: "Head of Ops",
    place: "Tema, GH",
    industry: "Distribution",
    score: 62,
    signals: 1,
    status: "Review",
  },
  {
    company: "Sahel Cold Chain",
    contact: "—",
    place: "Kano, NG",
    industry: "Cold storage",
    score: 38,
    signals: 0,
    status: "Low fit",
  },
];

/** The prospect table from PRD section 117. */
export function ProspectTablePanel() {
  return (
    <AppFrame label="Prospects — Nigeria + Kenya · ICP: Fleet operators">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead className="border-b border-border bg-bg">
            <tr>
              <Th>Company</Th>
              <Th className="hidden sm:table-cell">Buyer</Th>
              <Th className="hidden md:table-cell">Location</Th>
              <Th className="hidden lg:table-cell">Industry</Th>
              <Th>Score</Th>
              <Th className="hidden sm:table-cell">Signals</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {PROSPECTS.map((row) => (
              <tr key={row.company} className="transition-colors hover:bg-bg-subtle">
                <Td className="font-medium text-fg">{row.company}</Td>
                <Td className="hidden text-fg-muted sm:table-cell">{row.contact}</Td>
                <Td className="hidden text-fg-muted md:table-cell">{row.place}</Td>
                <Td className="hidden text-fg-muted lg:table-cell">{row.industry}</Td>
                <Td>
                  <ScoreBadge score={row.score} />
                </Td>
                <Td className="tabular hidden text-fg-muted sm:table-cell">
                  {row.signals}
                </Td>
                <Td>
                  <Badge
                    tone={
                      row.status === "Ready"
                        ? "positive"
                        : row.status === "Review"
                          ? "warm"
                          : "neutral"
                    }
                  >
                    {row.status}
                  </Badge>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-border px-4 py-2.5 text-xs text-fg-subtle">
        Ranked by opportunity score. Weights are configurable per workspace.
      </p>
    </AppFrame>
  );
}

const SIGNALS = [
  {
    headline: "Opened a second depot in Ibadan",
    source: "Company announcement",
    age: "6 days ago",
    confidence: 92,
    tone: "hot" as const,
  },
  {
    headline: "Hiring 12 drivers and a fleet supervisor",
    source: "Careers page",
    age: "2 days ago",
    confidence: 88,
    tone: "hot" as const,
  },
  {
    headline: "No telematics vendor detected on site",
    source: "Technology scan",
    age: "Today",
    confidence: 74,
    tone: "warm" as const,
  },
  {
    headline: "Published a delivery-SLA commitment",
    source: "Pricing page diff",
    age: "3 weeks ago",
    confidence: 61,
    tone: "cold" as const,
  },
];

/** Signals always carry source, time and confidence (PRD section 33). */
export function SignalEvidencePanel() {
  return (
    <AppFrame label="Buying signals — Harmattan Haulage">
      <ul className="divide-y divide-border">
        {SIGNALS.map((signal) => (
          <li key={signal.headline} className="flex items-start gap-3 px-4 py-3.5">
            <span
              aria-hidden
              className={cn(
                "mt-1.5 size-2 shrink-0 rounded-full",
                signal.tone === "hot"
                  ? "bg-signal-hot"
                  : signal.tone === "warm"
                    ? "bg-signal-warm"
                    : "bg-signal-cold",
              )}
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-fg">{signal.headline}</p>
              <p className="mt-0.5 text-xs text-fg-subtle">
                {signal.source} &middot; {signal.age}
              </p>
            </div>
            <Badge tone={signal.tone} className="tabular shrink-0">
              {signal.confidence}%
            </Badge>
          </li>
        ))}
      </ul>
      <p className="border-t border-border px-4 py-2.5 text-xs text-fg-subtle">
        Signals expire. A stale signal stops counting toward the score.
      </p>
    </AppFrame>
  );
}

/** The explainability format from PRD section 119. */
export function WhyContactPanel() {
  return (
    <AppFrame label="Why contact this company?">
      <div className="space-y-4 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="hot">High opportunity</Badge>
          <span className="tabular text-xs text-fg-subtle">Confidence 87%</span>
        </div>

        <p className="text-sm text-fg">
          Harmattan Haulage opened a second depot in Ibadan and is hiring drivers and a
          fleet supervisor. No telematics vendor is detected on their site, so fuel loss
          and SLA tracking across the new route is likely to be manual right now.
        </p>

        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">
            Evidence
          </p>
          <ul className="space-y-1.5">
            {[
              "Depot expansion — company announcement, 6 days ago",
              "Hiring 12 drivers — careers page, 2 days ago",
              "No telematics detected — technology scan, today",
              "Geography matches target market — Nigeria",
            ].map((item) => (
              <li key={item} className="flex gap-2 text-sm text-fg-muted">
                <span
                  aria-hidden
                  className="mt-2 size-1 shrink-0 rounded-full bg-accent"
                />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <p className="rounded-lg border border-border bg-bg px-3 py-2 text-xs text-fg-subtle">
          Each line links to its source. Where there is no evidence, the system says so
          rather than filling the gap.
        </p>
      </div>
    </AppFrame>
  );
}

/** Generic versus researched outreach, side by side. */
export function OutreachComparePanel() {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <AppFrame label="Generic template" className="shadow-[var(--shadow-card)]">
        <div className="space-y-2 p-5">
          <Badge tone="negative">Mass send</Badge>
          <p className="text-sm text-fg-muted">
            Hi {"{{first_name}}"}, I hope this email finds you well. We help companies
            like {"{{company}}"} improve efficiency with our best-in-class platform. Do
            you have 15 minutes this week for a quick call?
          </p>
          <p className="pt-1 text-xs text-fg-subtle">
            No reason to contact. No evidence. Indistinguishable from spam.
          </p>
        </div>
      </AppFrame>

      <AppFrame label="Researched — drafted from signals">
        <div className="space-y-2 p-5">
          <Badge tone="positive">Evidence-backed</Badge>
          <p className="text-sm text-fg">
            Hi Adaeze — saw the Ibadan depot opening and the driver hiring push. Teams
            adding a second route usually lose visibility on fuel and SLA first. We cut
            idle time for two Lagos fleets of a similar size. Worth 15 minutes?
          </p>
          <p className="pt-1 text-xs text-fg-subtle">
            Drafted from stored signals. You approve before anything sends.
          </p>
        </div>
      </AppFrame>
    </div>
  );
}

const AGENT_MODES = [
  {
    mode: "Manual",
    summary: "AI recommends. You write and send everything.",
    detail: "Suggestions and research only. No outbound action is ever taken for you.",
  },
  {
    mode: "Copilot",
    summary: "AI drafts. You approve every message.",
    detail:
      "Replies are classified and answers drafted, but nothing leaves without a click.",
  },
  {
    mode: "Autopilot",
    summary: "AI acts inside limits you define.",
    detail:
      "Requires an approved knowledge base, prohibited topics, escalation rules and rate limits. Every action is audit-logged.",
  },
];

/** The three agent modes from PRD section 41, with Autopilot's gating stated. */
export function AgentModesPanel() {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {AGENT_MODES.map((item, index) => (
        <div
          key={item.mode}
          className={cn(
            "flex flex-col gap-2 rounded-[var(--radius-card)] border bg-surface p-5",
            index === 1
              ? "border-accent/40 shadow-[var(--shadow-card)]"
              : "border-border",
          )}
        >
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-fg">{item.mode}</h3>
            {index === 1 ? <Badge tone="accent">Default</Badge> : null}
          </div>
          <p className="text-sm text-fg">{item.summary}</p>
          <p className="text-xs text-fg-subtle">{item.detail}</p>
        </div>
      ))}
    </div>
  );
}

const PIPELINE = [
  { stage: "Engaged", count: 24, tone: "cold" as const },
  { stage: "Qualified", count: 11, tone: "warm" as const },
  { stage: "Meeting", count: 6, tone: "warm" as const },
  { stage: "Won", count: 2, tone: "hot" as const },
];

export function PipelineBoardPanel() {
  return (
    <AppFrame label="Pipeline — Q4 Nigeria">
      <div className="grid grid-cols-2 gap-px bg-border lg:grid-cols-4">
        {PIPELINE.map((column) => (
          <div key={column.stage} className="bg-surface p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                {column.stage}
              </span>
              <span className="tabular text-xs text-fg-muted">{column.count}</span>
            </div>
            <div className="space-y-1.5">
              {Array.from({ length: Math.min(3, column.count) }).map((_, index) => (
                <div
                  key={index}
                  className="rounded-md border border-border bg-bg px-2 py-2"
                  aria-hidden
                >
                  <div className="h-1.5 w-2/3 rounded-full bg-border-strong" />
                  <div className="mt-1.5 h-1.5 w-1/3 rounded-full bg-border" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </AppFrame>
  );
}

/** Revenue attribution — the differentiator, so it gets the most weight. */
export function RevenuePanel() {
  return (
    <AppFrame label="Revenue attribution — by campaign">
      <div className="divide-y divide-border">
        <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
          {[
            { label: "Qualified", value: "38" },
            { label: "Meetings", value: "17" },
            { label: "Customers", value: "6" },
            { label: "Pipeline", value: "₦41.2M" },
          ].map((stat) => (
            <div key={stat.label} className="bg-surface px-4 py-5 text-center">
              <div className="tabular text-2xl font-semibold text-fg">{stat.value}</div>
              <div className="mt-0.5 text-xs text-fg-muted">{stat.label}</div>
            </div>
          ))}
        </div>

        <div className="space-y-2 p-4">
          {[
            { campaign: "Lagos fleet operators — expansion signal", won: 4, roi: "6.1x" },
            { campaign: "Nairobi distribution — hiring signal", won: 2, roi: "3.4x" },
            { campaign: "Ghana cold chain — broad ICP", won: 0, roi: "0.0x" },
          ].map((row) => (
            <div
              key={row.campaign}
              className="flex items-center justify-between gap-3 rounded-lg border border-border bg-bg px-3 py-2.5"
            >
              <span className="min-w-0 truncate text-sm text-fg">{row.campaign}</span>
              <span className="flex shrink-0 items-center gap-2">
                <span className="tabular text-xs text-fg-muted">{row.won} won</span>
                <Badge tone={row.won > 0 ? "positive" : "neutral"} className="tabular">
                  {row.roi}
                </Badge>
              </span>
            </div>
          ))}
        </div>
      </div>
      <p className="border-t border-border px-4 py-2.5 text-xs text-fg-subtle">
        The third campaign is losing money. That is the point of measuring it.
      </p>
    </AppFrame>
  );
}
