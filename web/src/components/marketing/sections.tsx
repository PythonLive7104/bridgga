import Link from "next/link";

import {
  AgentModesPanel,
  OutreachComparePanel,
  PipelineBoardPanel,
  RevenuePanel,
  SignalEvidencePanel,
  WhyContactPanel,
} from "@/components/marketing/panels";
import { Reveal } from "@/components/marketing/reveal";
import { Section, SectionHeading, StatBand } from "@/components/marketing/section";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

/* -------------------------------------------------------------------------- */
/* Problem                                                                     */
/* -------------------------------------------------------------------------- */

const SCORECARD = [
  { metric: "Emails sent", verdict: "Not a goal", tone: "negative" as const },
  { metric: "Database size", verdict: "Not a moat", tone: "negative" as const },
  { metric: "Open rate", verdict: "Weak proxy", tone: "warm" as const },
  { metric: "Qualified opportunities", verdict: "Counts", tone: "positive" as const },
  { metric: "Meetings booked", verdict: "Counts", tone: "positive" as const },
  { metric: "Revenue attributed", verdict: "The point", tone: "positive" as const },
];

export function ProblemSection() {
  return (
    <Section tone="subtle">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <Reveal>
          <SectionHeading
            align="left"
            eyebrow="The problem"
            title="Most sales tools optimise for activity. Activity is not revenue."
            description="Leads sourced, contacts enriched, emails sent, open rates, reply rates — a team can win on every one of those and still not sign a customer."
          />
          <p className="mt-4 max-w-xl text-fg-muted">
            The numbers that actually move a business sit further down the funnel, and
            almost nothing is built to optimise for them. So we measure ourselves on one
            thing: paying customers generated per account.
          </p>
        </Reveal>

        <Reveal delay={100}>
          <Card>
            <CardContent className="divide-y divide-border p-0">
              {SCORECARD.map((row) => (
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
        </Reveal>
      </div>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* The three questions (PRD section 136)                                       */
/* -------------------------------------------------------------------------- */

const PILLARS = [
  {
    label: "Prospect intelligence",
    question: "Who should I sell to?",
    answer:
      "An ideal customer profile built from your own site, then a ranked shortlist of companies that match it. You edit every field; nothing is a black box.",
  },
  {
    label: "Signals and evidence",
    question: "Why should I contact them now?",
    answer:
      "A buying signal with a source, a timestamp and a confidence score behind it. If we cannot show you the evidence, we say so instead of inventing it.",
  },
  {
    label: "Revenue attribution",
    question: "Did contacting them make money?",
    answer:
      "Every campaign traced through to meetings, opportunities and closed revenue. The dashboard leads with customers won, not emails sent.",
  },
];

export function ThreeQuestionsSection() {
  return (
    <Section>
      <Reveal>
        <SectionHeading
          eyebrow="What it is for"
          title="Three questions. Everything else supports them."
        />
      </Reveal>

      <div className="mt-14 grid gap-5 lg:grid-cols-3">
        {PILLARS.map((pillar, index) => (
          <Reveal key={pillar.question} delay={index * 90}>
            <Card className="h-full">
              <CardContent className="flex h-full flex-col gap-3 p-6">
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
          </Reveal>
        ))}
      </div>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Signals and evidence                                                        */
/* -------------------------------------------------------------------------- */

export function EvidenceSection() {
  return (
    <Section>
      <Reveal>
        <SectionHeading
          eyebrow="Signals and evidence"
          title="Why this company, and why now"
          description="A score you cannot interrogate is a guess with a number on it. Every signal carries its source, its timestamp and a confidence value, and every recommendation shows the evidence it rests on."
        />
      </Reveal>

      <div className="mt-14 grid gap-6 lg:grid-cols-2">
        <Reveal>
          <SignalEvidencePanel />
        </Reveal>
        <Reveal delay={100}>
          <WhyContactPanel />
        </Reveal>
      </div>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Outreach                                                                    */
/* -------------------------------------------------------------------------- */

export function OutreachSection() {
  return (
    <Section tone="subtle">
      <Reveal>
        <SectionHeading
          eyebrow="Outreach"
          title="Personalised because it was researched, not because it has a merge field"
          description="Messages are drafted from the stored signals, so the reason for contact is specific and checkable. Nothing sends without your approval."
        />
      </Reveal>

      <Reveal className="mt-14" delay={80}>
        <OutreachComparePanel />
      </Reveal>

      <Reveal className="mt-8" delay={140}>
        <div className="rounded-[var(--radius-card)] border border-border bg-surface p-5">
          <h3 className="text-sm font-semibold text-fg">Before anything launches</h3>
          <p className="mt-1 text-sm text-fg-muted">
            Every campaign shows its estimated audience, AI cost, message volume, sample
            messages and compliance warnings — and waits for a human to approve it.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {[
              "Estimated audience",
              "Estimated AI cost",
              "Sample messages",
              "Compliance warnings",
              "Sending limits",
              "Approval required",
            ].map((item) => (
              <Badge key={item}>{item}</Badge>
            ))}
          </div>
        </div>
      </Reveal>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* AI sales agent                                                              */
/* -------------------------------------------------------------------------- */

export function AgentSection() {
  return (
    <Section>
      <Reveal>
        <SectionHeading
          eyebrow="AI sales agent"
          title="You decide how much the AI is allowed to do"
          description="Three modes, and the most autonomous one is gated on policies you set. Autonomy you cannot constrain is a liability, not a feature."
        />
      </Reveal>

      <Reveal className="mt-14" delay={80}>
        <AgentModesPanel />
      </Reveal>

      <Reveal className="mt-6" delay={120}>
        <p className="mx-auto max-w-2xl text-center text-sm text-fg-subtle">
          The agent will classify a reply, draft an answer, detect an objection, propose a
          meeting — and stop contacting someone the moment they ask it to.
        </p>
      </Reveal>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Pipeline and revenue -- the differentiator, so it gets the most weight       */
/* -------------------------------------------------------------------------- */

export function RevenueSection() {
  return (
    <Section tone="wash">
      <Reveal>
        <SectionHeading
          eyebrow="Revenue attribution"
          title="Which campaigns are generating money?"
          description="The question most outbound tooling cannot answer. Every campaign traces through conversation, meeting, opportunity and deal to recorded revenue — so you can switch off the ones that are costing you."
        />
      </Reveal>

      <div className="mt-14 grid gap-6 lg:grid-cols-[1fr_1.15fr]">
        <Reveal>
          <PipelineBoardPanel />
        </Reveal>
        <Reveal delay={100}>
          <RevenuePanel />
        </Reveal>
      </div>

      <Reveal className="mt-10" delay={160}>
        <StatBand
          items={[
            { value: "Customers", label: "North-star metric" },
            { value: "Pipeline", label: "Open opportunity value" },
            { value: "CAC", label: "Cost per acquired customer" },
            { value: "ROI", label: "Return per campaign" },
          ]}
        />
        <p className="mt-3 text-center text-xs text-fg-subtle">
          What the dashboard leads with. Not emails sent, not credits consumed.
        </p>
      </Reveal>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Africa-first                                                                */
/* -------------------------------------------------------------------------- */

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

const CHANNEL_MIX = [
  { market: "Nigeria", channels: "Email + WhatsApp", currency: "NGN" },
  { market: "Kenya", channels: "Email + WhatsApp", currency: "KES" },
  { market: "South Africa", channels: "Email + LinkedIn", currency: "ZAR" },
  { market: "Ghana", channels: "Email + WhatsApp", currency: "GHS" },
  { market: "France", channels: "Email", currency: "EUR" },
];

export function AfricaSection() {
  return (
    <Section>
      <div className="grid items-start gap-12 lg:grid-cols-2">
        <Reveal>
          <SectionHeading
            align="left"
            eyebrow="Africa-first, not Africa-only"
            title="Built for African businesses. Ready for the world."
            description="Fragmented company data, WhatsApp-first buyers, multiple currencies and cross-border complexity are design requirements here, not edge cases."
          />
          <p className="mt-4 max-w-xl text-fg-muted">
            It works in both directions: African companies selling abroad, and
            international companies entering African markets.
          </p>

          <div className="mt-7 flex flex-wrap gap-2">
            {MARKETS.map((market) => (
              <Badge key={market}>{market}</Badge>
            ))}
          </div>
        </Reveal>

        <Reveal delay={100}>
          <Card>
            <CardContent className="p-0">
              <div className="border-b border-border px-5 py-3">
                <h3 className="text-sm font-semibold text-fg">Channel mix by market</h3>
                <p className="mt-0.5 text-xs text-fg-muted">
                  Defaults you can override per workspace.
                </p>
              </div>
              <dl className="divide-y divide-border">
                {CHANNEL_MIX.map((row) => (
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
        </Reveal>
      </div>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Integrations -- named in text, not as borrowed logos                        */
/* -------------------------------------------------------------------------- */

const INTEGRATION_GROUPS = [
  {
    group: "Email",
    items: ["Gmail", "Outlook", "SMTP", "Amazon SES", "SendGrid", "Postmark"],
  },
  {
    group: "Calendar",
    items: ["Google Calendar", "Microsoft Calendar", "Calendly", "Cal.com"],
  },
  { group: "CRM", items: ["HubSpot", "Salesforce", "Pipedrive", "Zoho", "Close"] },
  { group: "Messaging", items: ["WhatsApp Business Platform", "SMS"] },
  { group: "Payments", items: ["Paystack", "Flutterwave", "Stripe"] },
];

export function IntegrationsSection() {
  return (
    <Section tone="subtle">
      <Reveal>
        <SectionHeading
          eyebrow="Integrations"
          title="Works with the tools you already pay for"
          description="Connect your own mailbox and your own CRM. We do not ask you to migrate anything to get started."
        />
      </Reveal>

      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {INTEGRATION_GROUPS.map((group, index) => (
          <Reveal key={group.group} delay={index * 60}>
            <Card className="h-full">
              <CardContent className="p-5">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-fg-subtle">
                  {group.group}
                </h3>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {group.items.map((item) => (
                    <Badge key={item}>{item}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          </Reveal>
        ))}
      </div>

      <Reveal className="mt-6" delay={200}>
        <p className="text-center text-xs text-fg-subtle">
          Email and calendar first. CRM sync, WhatsApp and payments follow — see the
          roadmap rather than a promise.
        </p>
      </Reveal>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* FAQ -- question headings with direct answers (PRD section 20)               */
/* -------------------------------------------------------------------------- */

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
      "Unsubscribes suppress a person across your whole organization immediately and block re-enrolment. Email runs through your own verified domain with SPF, DKIM and DMARC guidance, and WhatsApp runs only on the official Business Platform.",
  },
  {
    question: "Does the AI ever send messages on its own?",
    answer:
      "Only if you turn that on, and only inside limits you set: an approved knowledge base, prohibited topics, escalation rules and rate limits, with every action in an audit log. The default is that AI drafts and you approve.",
  },
  {
    question: "Where does your data come from?",
    answer:
      "Licensed providers, public business information gathered lawfully, your own imports, and our own research. Every record keeps its source, the URL it came from and when it was collected, so you can check any claim we make.",
  },
  {
    question: "Why build this for African markets first?",
    answer:
      "Because fragmented company data, WhatsApp-first buyers, multiple currencies and cross-border complexity are design requirements here, not edge cases. Building for that produces a system that also works anywhere else.",
  },
];

export function FaqSection() {
  return (
    <Section tone="subtle" aria-labelledby="faq-heading">
      <div className="mx-auto max-w-3xl">
        <Reveal>
          <h2 id="faq-heading" className="text-headline text-center text-fg">
            Common questions
          </h2>
        </Reveal>

        <div className="mt-12 space-y-3">
          {FAQ.map((item, index) => (
            <Reveal key={item.question} delay={index * 50}>
              <details className="group rounded-[var(--radius-card)] border border-border bg-surface px-5 py-4 transition-colors hover:border-border-strong">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-medium text-fg">
                  {item.question}
                  <span
                    aria-hidden
                    className="shrink-0 text-lg leading-none text-fg-subtle transition-transform group-open:rotate-45"
                  >
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm text-fg-muted">{item.answer}</p>
              </details>
            </Reveal>
          ))}
        </div>
      </div>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Final CTA                                                                   */
/* -------------------------------------------------------------------------- */

export function FinalCtaSection() {
  return (
    <Section tone="wash">
      <div className="mx-auto max-w-2xl text-center">
        <Reveal>
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
        </Reveal>
      </div>
    </Section>
  );
}
