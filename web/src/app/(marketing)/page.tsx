import type { Metadata } from "next";
import Link from "next/link";

import { PipelineWalkthrough } from "@/components/marketing/pipeline-walkthrough";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Turn your website into a customer acquisition engine",
  description:
    "Palatial finds the companies most likely to need your product, identifies the right decision makers, starts relevant conversations, and connects every conversation to revenue.",
  alternates: { canonical: "/" },
};

/** The three questions the product exists to answer (PRD section 136). */
const PILLARS = [
  {
    question: "Who should I sell to?",
    answer:
      "An ideal customer profile built from your own site, then a ranked shortlist of companies that match it. You edit every field; nothing is a black box.",
    label: "Prospect intelligence",
  },
  {
    question: "Why should I contact them now?",
    answer:
      "A buying signal with a source, a timestamp and a confidence score behind it. If we cannot show you the evidence, we say so instead of inventing it.",
    label: "Signals and evidence",
  },
  {
    question: "Did contacting them make money?",
    answer:
      "Every campaign traced through to meetings, opportunities and closed revenue. The dashboard leads with customers won, not emails sent.",
    label: "Revenue attribution",
  },
];

const MARKETS = [
  "Nigeria",
  "Kenya",
  "Ghana",
  "South Africa",
  "Egypt",
  "Rwanda",
  "Uganda",
  "Tanzania",
  "Senegal",
  "Côte d'Ivoire",
];

/** Structured as question-then-direct-answer for generative search (PRD section 20). */
const FAQ = [
  {
    question: "What do I need before I start?",
    answer:
      "A website and something you sell to other businesses. We read the site, draft your ideal customer profile, and you correct it. No list to upload and no CRM to migrate first.",
  },
  {
    question: "Is this just a lead database?",
    answer:
      "No. A database answers 'who has an email address'. The harder question is which companies deserve your attention this week and why. That is what we score, explain and track through to revenue.",
  },
  {
    question: "How do you handle outreach compliance?",
    answer:
      "Unsubscribes suppress a person across your whole organization immediately and block re-enrolment. Email sending runs through your own verified domain with SPF, DKIM and DMARC guidance, and WhatsApp runs only on the official Business Platform.",
  },
  {
    question: "Does the AI ever send messages on its own?",
    answer:
      "Only if you turn that on, and only inside limits you set: an approved knowledge base, prohibited topics, escalation rules and rate limits, with every action in an audit log. The default is that AI drafts and you approve.",
  },
  {
    question: "Why build this for African markets first?",
    answer:
      "Because fragmented company data, WhatsApp-first buyers, multiple currencies and cross-border complexity are design requirements here, not edge cases. Building for that produces a system that also works anywhere else.",
  },
];

export default function HomePage() {
  return (
    <>
      {/* ------------------------------------------------------------------ *
       * Hero
       * ------------------------------------------------------------------ */}
      <section className="gradient-wash">
        <div className="mx-auto max-w-6xl px-4 pb-16 pt-20 sm:pb-24 sm:pt-28">
          <div className="mx-auto max-w-3xl text-center">
            <Badge tone="accent">AI Customer Acquisition OS</Badge>

            <h1 className="text-display mt-6 text-fg">
              Turn your website into a customer acquisition engine
            </h1>

            <p className="mx-auto mt-6 max-w-2xl text-lg text-fg-muted">
              AI finds the companies most likely to need your product, identifies the
              right decision makers, starts relevant conversations, and helps turn
              prospects into paying customers.
            </p>

            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                href="/auth/signup"
                className="inline-flex h-12 w-full items-center justify-center rounded-[var(--radius-control)] bg-accent px-7 text-base font-medium text-accent-fg transition-colors hover:bg-accent-hover sm:w-auto"
              >
                Find my customers
              </Link>
              <Link
                href="#walkthrough-heading"
                className="inline-flex h-12 w-full items-center justify-center rounded-[var(--radius-control)] border border-border bg-surface px-7 text-base font-medium text-fg transition-colors hover:border-border-strong sm:w-auto"
              >
                See how it works
              </Link>
            </div>

            <p className="mt-5 text-sm text-fg-subtle">
              Start free. No list to upload, no card required to see your first
              prospects.
            </p>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------------ *
       * Problem
       * ------------------------------------------------------------------ */}
      <section className="border-y border-border bg-bg-subtle">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:py-20">
          <div className="grid items-center gap-10 lg:grid-cols-2">
            <div>
              <h2 className="text-headline text-fg">
                Most sales tools optimise for activity. Activity is not revenue.
              </h2>
              <p className="mt-5 text-fg-muted">
                Leads sourced, contacts enriched, emails sent, open rates, reply rates
                &mdash; a team can win on every one of those and still not sign a
                customer. The numbers that move are further down the funnel, and almost
                nothing is built to optimise for them.
              </p>
              <p className="mt-4 text-fg-muted">
                So we measure ourselves on one thing: paying customers generated per
                account.
              </p>
            </div>

            <Card>
              <CardContent className="divide-y divide-border p-0">
                {[
                  { metric: "Emails sent", verdict: "Not a goal", tone: "negative" as const },
                  { metric: "Database size", verdict: "Not a moat", tone: "negative" as const },
                  { metric: "Open rate", verdict: "Weak proxy", tone: "warm" as const },
                  { metric: "Qualified opportunities", verdict: "Counts", tone: "positive" as const },
                  { metric: "Meetings booked", verdict: "Counts", tone: "positive" as const },
                  { metric: "Revenue attributed", verdict: "The point", tone: "positive" as const },
                ].map((row) => (
                  <div
                    key={row.metric}
                    className="flex items-center justify-between gap-4 px-5 py-3.5"
                  >
                    <span className="text-sm text-fg">{row.metric}</span>
                    <Badge tone={row.tone}>{row.verdict}</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------------ *
       * How it works
       * ------------------------------------------------------------------ */}
      <PipelineWalkthrough />

      {/* ------------------------------------------------------------------ *
       * The three questions
       * ------------------------------------------------------------------ */}
      <section className="border-t border-border bg-bg-subtle">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:py-24">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-headline text-fg">
              Three questions. Everything else supports them.
            </h2>
          </div>

          <div className="mt-12 grid gap-5 lg:grid-cols-3">
            {PILLARS.map((pillar, index) => (
              <Card key={pillar.question} className="flex flex-col">
                <CardContent className="flex flex-1 flex-col gap-3 p-6">
                  <div className="flex items-center gap-2">
                    <span
                      aria-hidden
                      className="tabular grid size-6 place-items-center rounded-full bg-accent-subtle text-xs font-semibold text-accent"
                    >
                      {index + 1}
                    </span>
                    <Badge>{pillar.label}</Badge>
                  </div>
                  <h3 className="text-lg font-semibold tracking-tight text-fg">
                    {pillar.question}
                  </h3>
                  <p className="text-sm text-fg-muted">{pillar.answer}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------------ *
       * Africa-first
       * ------------------------------------------------------------------ */}
      <section className="mx-auto max-w-6xl px-4 py-20 sm:py-24">
        <div className="grid items-start gap-10 lg:grid-cols-2">
          <div>
            <Badge tone="accent">Africa-first, not Africa-only</Badge>
            <h2 className="text-headline mt-4 text-fg">
              Built for African businesses. Ready for the world.
            </h2>
            <p className="mt-5 text-fg-muted">
              Country-level business intelligence, local currencies, WhatsApp as a
              first-class channel, and per-market channel preferences &mdash; because
              the way a Lagos fleet operator buys is not the way a London SaaS buyer
              does.
            </p>
            <p className="mt-4 text-fg-muted">
              It works in both directions: African companies selling abroad, and
              international companies entering African markets.
            </p>

            <div className="mt-7 flex flex-wrap gap-2">
              {MARKETS.map((market) => (
                <Badge key={market}>{market}</Badge>
              ))}
            </div>
          </div>

          <Card>
            <CardContent className="p-0">
              <div className="border-b border-border px-5 py-3">
                <h3 className="text-sm font-semibold text-fg">
                  Channel mix by market
                </h3>
                <p className="mt-0.5 text-xs text-fg-muted">
                  Defaults you can override per workspace.
                </p>
              </div>
              <dl className="divide-y divide-border">
                {[
                  { market: "Nigeria", channels: "Email + WhatsApp", currency: "NGN" },
                  { market: "Kenya", channels: "Email + WhatsApp", currency: "KES" },
                  { market: "South Africa", channels: "Email + LinkedIn", currency: "ZAR" },
                  { market: "Ghana", channels: "Email + WhatsApp", currency: "GHS" },
                  { market: "France", channels: "Email", currency: "EUR" },
                ].map((row) => (
                  <div
                    key={row.market}
                    className="flex items-center justify-between gap-4 px-5 py-3"
                  >
                    <dt className="text-sm text-fg">{row.market}</dt>
                    <dd className="flex items-center gap-2">
                      <span className="text-sm text-fg-muted">{row.channels}</span>
                      <Badge>{row.currency}</Badge>
                    </dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* ------------------------------------------------------------------ *
       * FAQ -- question headings with direct answers (PRD section 20)
       * ------------------------------------------------------------------ */}
      <section
        aria-labelledby="faq-heading"
        className="border-t border-border bg-bg-subtle"
      >
        <div className="mx-auto max-w-3xl px-4 py-20 sm:py-24">
          <h2 id="faq-heading" className="text-headline text-center text-fg">
            Common questions
          </h2>

          <div className="mt-10 space-y-3">
            {FAQ.map((item) => (
              <details
                key={item.question}
                className="group rounded-[var(--radius-card)] border border-border bg-surface px-5 py-4"
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-medium text-fg">
                  {item.question}
                  <span
                    aria-hidden
                    className="shrink-0 text-fg-subtle transition-transform group-open:rotate-45"
                  >
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm text-fg-muted">{item.answer}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------------ *
       * Final CTA
       * ------------------------------------------------------------------ */}
      <section className="gradient-wash border-t border-border">
        <div className="mx-auto max-w-3xl px-4 py-20 text-center sm:py-24">
          <h2 className="text-headline text-fg">
            Find out who actually needs what you sell
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-fg-muted">
            Start with your website. We will come back with a profile, a market, and a
            shortlist you can argue with.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/auth/signup"
              className="inline-flex h-12 w-full items-center justify-center rounded-[var(--radius-control)] bg-accent px-7 text-base font-medium text-accent-fg transition-colors hover:bg-accent-hover sm:w-auto"
            >
              Find my customers
            </Link>
            <Link
              href="/contact"
              className="inline-flex h-12 w-full items-center justify-center rounded-[var(--radius-control)] border border-border bg-surface px-7 text-base font-medium text-fg transition-colors hover:border-border-strong sm:w-auto"
            >
              Talk to us
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
