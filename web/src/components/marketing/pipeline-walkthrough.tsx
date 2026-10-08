"use client";

import * as React from "react";

import { Badge, ScoreBadge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * The homepage centrepiece: the whole journey from a website URL to attributed
 * revenue, shown as a stepper.
 *
 * Two deliberate choices:
 *
 * 1. Every panel is built from the same primitives the product UI uses, with
 *    seeded demo data, rather than from screenshots. Screenshots go stale the
 *    moment the app changes, cannot be translated, and are invisible to search
 *    engines and screen readers.
 * 2. The data is obviously illustrative -- fictional companies, labelled as a
 *    demo -- because PRD section 8.3 asks for evidence over AI theatre, and
 *    inventing plausible-looking customer results on a marketing page is the
 *    opposite of that.
 */

const ADVANCE_MS = 5200;

interface Step {
  id: string;
  label: string;
  caption: string;
  panel: React.ReactNode;
}

function Panel({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-full flex-col gap-4">
      <div>
        <h3 className="text-sm font-semibold text-fg">{title}</h3>
        <p className="mt-0.5 text-sm text-fg-muted">{hint}</p>
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}

function Row({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-lg border border-border bg-bg px-3 py-2.5",
        className,
      )}
    >
      {children}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-bg px-3 py-2">
      <dt className="text-[11px] uppercase tracking-wide text-fg-subtle">{label}</dt>
      <dd className="mt-0.5 text-sm text-fg">{value}</dd>
    </div>
  );
}

const STEPS: Step[] = [
  {
    id: "understand",
    label: "Read the website",
    caption: "One URL in. The product, the buyer and the pitch come back editable.",
    panel: (
      <Panel
        title="What we understood"
        hint="Every field is a draft you can correct before anything is built on it."
      >
        <dl className="grid gap-2 sm:grid-cols-2">
          <Field label="Product" value="Fleet telematics for logistics operators" />
          <Field label="Business model" value="B2B SaaS, per-vehicle monthly" />
          <Field label="Sells to" value="Operations and fleet directors" />
          <Field label="Solves" value="Fuel loss, idle time, delivery SLA misses" />
        </dl>
      </Panel>
    ),
  },
  {
    id: "icp",
    label: "Build the ICP",
    caption: "Who to sell to, as a profile you own rather than a filter you guess at.",
    panel: (
      <Panel title="Ideal customer profile" hint="Draft generated, then edited by you.">
        <div className="space-y-2">
          <Row>
            <span className="text-sm text-fg-muted">Industry</span>
            <span className="text-sm text-fg">Logistics, distribution, haulage</span>
          </Row>
          <Row>
            <span className="text-sm text-fg-muted">Size</span>
            <span className="text-sm text-fg">25&ndash;250 staff, 20+ vehicles</span>
          </Row>
          <Row>
            <span className="text-sm text-fg-muted">Buyer</span>
            <span className="text-sm text-fg">Head of Operations, Fleet Manager</span>
          </Row>
          <Row>
            <span className="text-sm text-fg-muted">Pain signals</span>
            <span className="flex gap-1">
              <Badge tone="accent">Hiring drivers</Badge>
              <Badge tone="accent">New depot</Badge>
            </span>
          </Row>
        </div>
      </Panel>
    ),
  },
  {
    id: "markets",
    label: "Pick the markets",
    caption: "Ranked by fit, with the reasoning attached to each one.",
    panel: (
      <Panel title="Recommended markets" hint="Each score carries its reasoning.">
        <div className="space-y-2">
          {[
            { market: "Nigeria", fit: "High fit", reason: "Dense haulage sector, email + WhatsApp reach" },
            { market: "Kenya", fit: "High fit", reason: "Regional distribution hub, strong SaaS adoption" },
            { market: "Ghana", fit: "Medium fit", reason: "Smaller fleet operator base" },
          ].map((row) => (
            <Row key={row.market} className="flex-col items-start sm:flex-row sm:items-center">
              <div>
                <div className="text-sm font-medium text-fg">{row.market}</div>
                <div className="text-xs text-fg-muted">{row.reason}</div>
              </div>
              <Badge tone={row.fit === "High fit" ? "positive" : "warm"}>{row.fit}</Badge>
            </Row>
          ))}
        </div>
      </Panel>
    ),
  },
  {
    id: "prospects",
    label: "Score the prospects",
    caption: "A ranked shortlist, not a list of everyone who happens to have an email.",
    panel: (
      <Panel
        title="Prospects, ranked"
        hint="Scored on fit, intent and evidence. Weights are yours to change."
      >
        <div className="space-y-2">
          {[
            { company: "Harmattan Haulage", place: "Lagos, NG", score: 91 },
            { company: "Rift Valley Freight", place: "Nairobi, KE", score: 84 },
            { company: "Volta Distribution", place: "Tema, GH", score: 62 },
            { company: "Sahel Cold Chain", place: "Kano, NG", score: 38 },
          ].map((row) => (
            <Row key={row.company}>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-fg">{row.company}</div>
                <div className="text-xs text-fg-muted">{row.place}</div>
              </div>
              <ScoreBadge score={row.score} />
            </Row>
          ))}
        </div>
      </Panel>
    ),
  },
  {
    id: "signals",
    label: "Show the evidence",
    caption: "Why this company, and why now — with the source behind every claim.",
    panel: (
      <Panel
        title="Why contact Harmattan Haulage?"
        hint="Confidence 87%. Every line below links to where it came from."
      >
        <div className="space-y-2">
          {[
            { signal: "Opened a second depot in Ibadan", source: "Company announcement", age: "6 days ago" },
            { signal: "Hiring 12 drivers and a fleet supervisor", source: "Careers page", age: "2 days ago" },
            { signal: "No telematics vendor detected", source: "Website technology scan", age: "Today" },
          ].map((row) => (
            <Row key={row.signal} className="flex-col items-start gap-1 sm:flex-row sm:items-center">
              <div className="min-w-0">
                <div className="text-sm text-fg">{row.signal}</div>
                <div className="text-xs text-fg-subtle">
                  {row.source} &middot; {row.age}
                </div>
              </div>
              <Badge tone="hot">Signal</Badge>
            </Row>
          ))}
        </div>
      </Panel>
    ),
  },
  {
    id: "revenue",
    label: "Tie it to revenue",
    caption: "Which campaigns produced customers, not which produced activity.",
    panel: (
      <Panel
        title="Campaign contribution"
        hint="The only question that settles whether any of this worked."
      >
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            { label: "Qualified", value: "38" },
            { label: "Meetings", value: "17" },
            { label: "Customers", value: "6" },
            { label: "Pipeline", value: "₦41.2M" },
          ].map((stat) => (
            <div
              key={stat.label}
              className="rounded-lg border border-border bg-bg px-3 py-3 text-center"
            >
              <div className="tabular text-xl font-semibold text-fg">{stat.value}</div>
              <div className="mt-0.5 text-xs text-fg-muted">{stat.label}</div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-fg-subtle">
          Illustrative figures from a demo workspace, not a customer result.
        </p>
      </Panel>
    ),
  },
];

export function PipelineWalkthrough() {
  const [active, setActive] = React.useState(0);
  const [paused, setPaused] = React.useState(false);

  React.useEffect(() => {
    if (paused) return;

    // Honour the OS setting rather than only the CSS media query: this timer
    // moves content, which a CSS transition override cannot stop.
    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) return;

    const timer = window.setTimeout(
      () => setActive((current) => (current + 1) % STEPS.length),
      ADVANCE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [active, paused]);

  const activeStep = STEPS[active] ?? STEPS[0]!;

  return (
    <section
      aria-labelledby="walkthrough-heading"
      className="mx-auto max-w-6xl px-4 py-20 sm:py-28"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
    >
      <div className="mx-auto max-w-2xl text-center">
        <Badge tone="accent">How it works</Badge>
        <h2 id="walkthrough-heading" className="text-headline mt-4 text-fg">
          From a URL to attributed revenue
        </h2>
        <p className="mt-4 text-fg-muted">
          Nine steps run between a website and a closed deal. Here are the six that
          decide whether the other three are worth anyone&apos;s time.
        </p>
      </div>

      <div className="mt-12 grid gap-6 lg:grid-cols-[18rem_1fr]">
        {/* Step list doubles as the tab list. */}
        <div
          role="tablist"
          aria-label="Pipeline steps"
          aria-orientation="vertical"
          className="flex gap-2 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0"
        >
          {STEPS.map((step, index) => {
            const selected = index === active;
            return (
              <button
                key={step.id}
                role="tab"
                id={`tab-${step.id}`}
                aria-selected={selected}
                aria-controls={`panel-${step.id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => setActive(index)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown" || event.key === "ArrowRight") {
                    event.preventDefault();
                    setActive((current) => (current + 1) % STEPS.length);
                  }
                  if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
                    event.preventDefault();
                    setActive((current) => (current - 1 + STEPS.length) % STEPS.length);
                  }
                }}
                className={cn(
                  "shrink-0 rounded-[var(--radius-control)] border px-3 py-3 text-left transition-colors lg:shrink",
                  selected
                    ? "border-accent/40 bg-accent-subtle"
                    : "border-border bg-surface hover:border-border-strong",
                )}
              >
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className={cn(
                      "tabular grid size-5 shrink-0 place-items-center rounded-full text-[11px] font-semibold",
                      selected
                        ? "bg-accent text-accent-fg"
                        : "bg-bg-subtle text-fg-subtle",
                    )}
                  >
                    {index + 1}
                  </span>
                  <span
                    className={cn(
                      "whitespace-nowrap text-sm font-medium lg:whitespace-normal",
                      selected ? "text-fg" : "text-fg-muted",
                    )}
                  >
                    {step.label}
                  </span>
                </span>
                <span className="mt-1 hidden text-xs text-fg-subtle lg:block">
                  {step.caption}
                </span>
              </button>
            );
          })}
        </div>

        <div
          role="tabpanel"
          id={`panel-${activeStep.id}`}
          aria-labelledby={`tab-${activeStep.id}`}
          className="min-h-[22rem] rounded-[var(--radius-card)] border border-border bg-surface p-5 shadow-[var(--shadow-card)] sm:p-6"
        >
          {activeStep.panel}
        </div>
      </div>
    </section>
  );
}
