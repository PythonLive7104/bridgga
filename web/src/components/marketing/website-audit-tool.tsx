"use client";

import { AlertTriangle, ArrowRight, Check, Loader2, Search, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch, ApiError } from "@/lib/api/client";
import type { WebsiteAudit, WebsiteAuditCheck } from "@/lib/api/types";
import { cn, scoreBand } from "@/lib/utils";

/**
 * The free website sales audit (PRD sections 17 and 49).
 *
 * **The result is shown in full, immediately, to anybody.** Section 17 asks
 * for a useful free result and an *optional* signup, in that order. Gating
 * the findings behind an email turns the tool into an ad with a text field,
 * and the people worth reaching are exactly the ones who will not pay that
 * price to a product they have not seen work.
 *
 * **Failures lead, not the score.** A number at the top is a vanity metric; a
 * reader came to find out what to change. The failed checks are listed first,
 * heaviest first, each with its fix, and the passing ones are available
 * underneath for anyone who wants to see what was looked at.
 *
 * **Measured and judged are labelled.** Five of the eight dimensions are
 * counted from the HTML and three are a model's opinion. A reader who knows
 * their own site will test the first thing they can check, so the distinction
 * is on the page rather than in a footnote.
 */

const DIMENSION_LABELS: Record<string, string> = {
  value_proposition: "Value proposition",
  icp_clarity: "ICP clarity",
  conversion: "Conversion",
  cta: "Calls to action",
  trust: "Trust",
  pricing_clarity: "Pricing clarity",
  seo: "SEO",
  aeo: "AEO readiness",
};

const JUDGED = new Set(["value_proposition", "icp_clarity", "conversion"]);

function ScoreRing({ score, band }: { score: number; band: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="tabular text-5xl font-semibold tracking-tight text-fg">
        {score}
      </span>
      <span className="text-sm text-fg-subtle">/100</span>
      <Badge tone={scoreBand(score)} className="ml-2 capitalize">
        {band}
      </Badge>
    </div>
  );
}

function DimensionRow({
  dimension,
  score,
  note,
}: {
  dimension: string;
  score: number;
  note?: string;
}) {
  return (
    <li className="space-y-1 py-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-fg">
          {DIMENSION_LABELS[dimension] ?? dimension}
          <span className="ml-2 text-xs text-fg-subtle">
            {JUDGED.has(dimension) ? "judged" : "measured"}
          </span>
        </span>
        <span className="tabular text-sm text-fg-muted">{score}</span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-bg-subtle">
        <div
          className={cn(
            "h-full rounded-full",
            score >= 75
              ? "bg-signal-hot"
              : score >= 45
                ? "bg-signal-warm"
                : "bg-signal-cold",
          )}
          style={{ width: `${score}%` }}
        />
      </div>
      {note ? <p className="text-xs text-fg-subtle">{note}</p> : null}
    </li>
  );
}

function CheckRow({ check }: { check: WebsiteAuditCheck }) {
  return (
    <li className="flex gap-2 py-2">
      {check.passed ? (
        <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-positive" />
      ) : (
        <X aria-hidden className="mt-0.5 size-4 shrink-0 text-negative" />
      )}
      <div className="min-w-0">
        <p className="text-sm text-fg">{check.detail}</p>
        {check.fix ? <p className="text-xs text-fg-muted">{check.fix}</p> : null}
      </div>
      <span className="ml-auto shrink-0 text-xs text-fg-subtle">
        {DIMENSION_LABELS[check.dimension] ?? check.dimension}
      </span>
    </li>
  );
}

function Result({ audit }: { audit: WebsiteAudit }) {
  const [showPassing, setShowPassing] = React.useState(false);
  const passing = audit.checks.filter((check) => check.passed);

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-4 p-5">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-fg-subtle">
                {audit.domain || audit.url}
              </p>
              <ScoreRing score={audit.overall_score} band={audit.band} />
            </div>
            {audit.what_they_sell ? (
              <div className="max-w-sm text-sm text-fg-muted">
                <p>
                  <span className="text-fg-subtle">Reads as: </span>
                  {audit.what_they_sell}
                </p>
                <p>
                  <span className="text-fg-subtle">For: </span>
                  {audit.who_its_for || (
                    <span className="text-signal-warm">
                      the page does not say who it is for
                    </span>
                  )}
                </p>
              </div>
            ) : null}
          </div>

          {!audit.judged ? (
            // Said plainly rather than hidden. A reader is entitled to know
            // that three of the eight dimensions are missing from this run.
            <p className="flex items-start gap-1.5 text-xs text-signal-warm">
              <AlertTriangle aria-hidden className="mt-0.5 size-3 shrink-0" />
              The measured checks ran, but the judgement pass did not. Value proposition,
              ICP clarity and conversion are not scored here.
            </p>
          ) : null}

          <ul className="divide-y divide-border/60">
            {Object.entries(audit.scores).map(([dimension, score]) => (
              <DimensionRow
                key={dimension}
                dimension={dimension}
                score={score}
                note={audit.notes[dimension]}
              />
            ))}
          </ul>
        </CardContent>
      </Card>

      {audit.failed_checks.length ? (
        <section>
          <h2 className="text-sm font-semibold text-fg">
            {audit.failed_checks.length} thing
            {audit.failed_checks.length === 1 ? "" : "s"} to fix
          </h2>
          <p className="mt-1 text-sm text-fg-muted">
            Heaviest first. Every one of these was counted from your HTML, so you can
            check it yourself.
          </p>
          <Card className="mt-3">
            <CardContent className="p-4">
              <ul className="divide-y divide-border/60">
                {audit.failed_checks.map((check) => (
                  <CheckRow key={check.id} check={check} />
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>
      ) : (
        <p className="text-sm text-fg-muted">
          Every measured check passed. That is rare.
        </p>
      )}

      {audit.recommendations.length ? (
        <section>
          <h2 className="text-sm font-semibold text-fg">What to do about it</h2>
          <ul className="mt-3 space-y-3">
            {audit.recommendations.map((item, index) => (
              <li key={index}>
                <Card>
                  <CardContent className="p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-fg">{item.title}</p>
                      {/* Impact and effort together are what make a list of
                          suggestions an order of work. */}
                      <Badge tone={item.impact === "high" ? "accent" : "neutral"}>
                        {item.impact} impact
                      </Badge>
                      <Badge tone="neutral">{item.effort} effort</Badge>
                    </div>
                    {item.detail ? (
                      <p className="mt-1 text-sm text-fg-muted">{item.detail}</p>
                    ) : null}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <h2 className="text-sm font-semibold text-fg">Performance observations</h2>
        <p className="mt-1 text-sm text-fg-muted">
          Measurements, not a score — real performance needs a browser and a network
          trace, and a number here would be false precision.
        </p>
        <Card className="mt-3">
          <CardContent className="p-4">
            <dl className="grid gap-3 sm:grid-cols-2">
              {audit.performance.map((item) => (
                <div key={item.label}>
                  <dt className="text-xs uppercase tracking-wide text-fg-subtle">
                    {item.label}
                  </dt>
                  <dd className="text-sm text-fg">{item.value}</dd>
                  {item.note ? (
                    <dd className="text-xs text-signal-warm">{item.note}</dd>
                  ) : null}
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      </section>

      {showPassing ? (
        <Card>
          <CardContent className="p-4">
            <ul className="divide-y divide-border/60">
              {passing.map((check) => (
                <CheckRow key={check.id} check={check} />
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : (
        <Button variant="ghost" size="sm" onClick={() => setShowPassing(true)}>
          Show the {passing.length} checks that passed
        </Button>
      )}

      <Card className="gradient-wash">
        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <p className="text-sm font-medium text-fg">
              This is one page. Bridgga reads your whole site.
            </p>
            <p className="text-sm text-fg-muted">
              Then it finds the companies most likely to need what you sell, and tells you
              why to contact each one.
            </p>
          </div>
          <Link
            href="/auth/signup"
            className="inline-flex h-11 items-center justify-center gap-2 rounded-[var(--radius-control)] bg-accent px-6 text-sm font-medium text-accent-fg transition-colors hover:bg-accent-hover"
          >
            Find my customers
            <ArrowRight aria-hidden className="size-4" />
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

export function WebsiteAuditTool() {
  const [url, setUrl] = React.useState("");
  const [audit, setAudit] = React.useState<WebsiteAudit | null>(null);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!url.trim() || running) return;

    setRunning(true);
    setError("");
    try {
      const result = await apiFetch<WebsiteAudit>("/api/v1/tools/website-audit", {
        method: "POST",
        body: { url: url.trim() },
      });
      setAudit(result);
      if (result.status !== "ready") {
        setError(result.error_reason || "That page could not be read.");
      }
    } catch (caught) {
      // A throttle is the likely failure here, and "too many requests" is a
      // sentence, not a status code.
      setError(
        caught instanceof ApiError && caught.status === 429
          ? "That is a lot of audits. Give it a minute and try again."
          : "Something went wrong running the audit. Try again in a moment.",
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-16 sm:py-24">
      <h1 className="text-3xl font-semibold tracking-tight text-fg sm:text-4xl">
        What does your homepage tell a buyer?
      </h1>
      <p className="mt-3 max-w-2xl text-fg-muted">
        Paste a URL. You will get eight scores, every finding with the fix for it, and no
        account. Five of the eight are counted directly from your HTML, so you can check
        them yourself.
      </p>

      <form onSubmit={submit} className="mt-6 flex flex-wrap items-end gap-3">
        <Input
          label="Website"
          type="text"
          inputMode="url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="yourcompany.com"
          className="min-w-64 flex-1"
          autoComplete="url"
        />
        <Button type="submit" loading={running} disabled={!url.trim()}>
          {running ? (
            <Loader2 aria-hidden className="size-4 animate-spin" />
          ) : (
            <Search aria-hidden className="size-4" />
          )}
          Audit my site
        </Button>
      </form>

      {error ? (
        <p role="alert" className="mt-3 text-sm text-negative">
          {error}
        </p>
      ) : null}

      {audit && audit.status === "ready" ? (
        <div className="mt-10">
          <Result audit={audit} />
        </div>
      ) : null}
    </div>
  );
}
