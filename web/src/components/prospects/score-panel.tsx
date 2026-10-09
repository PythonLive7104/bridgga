"use client";

import { AlertTriangle, ExternalLink, Quote } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import type { ScoreComponentResult, ScoreExplanation } from "@/lib/api/types";
import { useProspectScore } from "@/lib/hooks/use-prospects";
import { cn, scoreBand } from "@/lib/utils";

/**
 * Why a prospect scores what it scores (PRD sections 32 and 119).
 *
 * Section 32 ends with "The platform must explain the score", and section 119
 * says what explaining means: recommendation, reason, evidence, confidence,
 * editable assumptions. All five are here, and two of them are the ones a
 * dashboard usually drops.
 *
 * **What was not assessed is shown as prominently as what was.** A score of
 * 82 from three components is a different claim from 82 from eight, and the
 * only honest way to show the difference is to say which three. The bar for
 * each component shows its *effective* weight — what it actually counted for
 * once the unassessable ones were dropped — because the gap between that and
 * the configured weight is the question people ask first.
 *
 * **The evidence is quoted inline.** A rep about to mention a signal to a real
 * buyer needs to read it before they do, not trust a number that read it for
 * them.
 */

function ComponentRow({ component }: { component: ScoreComponentResult }) {
  const share = component.available ? component.effective_weight : 0;
  const earned = component.points ?? 0;

  return (
    <li className="space-y-1 py-2">
      <div className="flex items-baseline justify-between gap-3">
        <span
          className={cn(
            "text-sm",
            component.available ? "text-fg" : "text-fg-subtle italic",
          )}
        >
          {component.label}
        </span>
        <span className="tabular shrink-0 text-xs text-fg-subtle">
          {component.available ? (
            <>
              {earned.toFixed(0)} of {share.toFixed(0)}
            </>
          ) : (
            "not assessed"
          )}
        </span>
      </div>

      {component.available ? (
        <div
          className="h-1 overflow-hidden rounded-full bg-bg-subtle"
          role="img"
          aria-label={`${component.label}: ${earned.toFixed(0)} of ${share.toFixed(0)} points`}
        >
          <div
            className="h-full rounded-full bg-accent"
            style={{ width: `${share ? Math.min((earned / share) * 100, 100) : 0}%` }}
          />
        </div>
      ) : null}

      <p className="text-xs text-fg-subtle">{component.reason}</p>

      {/* The configured weight versus what it counted for. Shown only when
          they differ, which is when the question comes up. */}
      {component.available &&
      Math.abs(component.effective_weight - component.weight) >= 1 ? (
        <p className="text-xs text-fg-subtle">
          Weighted {component.weight}%, counted for{" "}
          {component.effective_weight.toFixed(0)}% because other components could not be
          assessed.
        </p>
      ) : null}
    </li>
  );
}

function EvidenceItem({ entry }: { entry: ScoreExplanation["evidence"][number] }) {
  return (
    <li className="text-xs text-fg-muted">
      <p className="flex items-start gap-1.5">
        {entry.quote ? (
          <Quote aria-hidden className="mt-0.5 size-3 shrink-0 text-fg-subtle" />
        ) : null}
        <span>
          {entry.quote ? <em>&ldquo;{entry.quote}&rdquo;</em> : entry.claim}
          {entry.signal_type ? (
            <span className="ml-1.5 text-fg-subtle">
              ({entry.signal_type.replace(/_/g, " ")})
            </span>
          ) : null}
        </span>
      </p>
      {entry.source_url ? (
        <a
          href={entry.source_url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="inline-flex items-center gap-1 text-accent underline-offset-2 hover:underline"
        >
          {entry.source_type.replace(/_/g, " ") || "source"}
          <ExternalLink aria-hidden className="size-3" />
        </a>
      ) : null}
    </li>
  );
}

export function ScorePanel({ prospectId }: { prospectId: string }) {
  const { data, isLoading, error } = useProspectScore(prospectId);

  if (isLoading) {
    return <p className="p-4 text-sm text-fg-subtle">Working out the score…</p>;
  }
  if (error || !data) {
    return (
      <p className="p-4 text-sm text-fg-subtle">
        The score could not be explained right now.
      </p>
    );
  }

  const assumptions = data.assumptions;

  return (
    <div className="grid gap-5 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={scoreBand(data.score)} className="tabular">
            {data.recommendation}
          </Badge>
          <span className="tabular text-sm text-fg">{data.score}/100</span>
          {/* Confidence sits next to the score, never behind it: it is what
              turns "82" into a claim a reader can size up. */}
          <span className="text-xs text-fg-subtle">
            {data.confidence}% confidence — {Math.round(data.coverage * 100)}% of the
            weighting could be assessed
          </span>
        </div>

        <p className="text-sm text-fg-muted">{data.reason}</p>

        {assumptions.company_record_is_stale ? (
          <p className="flex items-start gap-1.5 text-xs text-signal-warm">
            <AlertTriangle aria-hidden className="mt-0.5 size-3 shrink-0" />
            Nothing has re-confirmed this company&rsquo;s details recently, so the
            confidence is discounted.
          </p>
        ) : null}

        {data.evidence.length ? (
          <div>
            <h4 className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
              Evidence
            </h4>
            <ul className="mt-1.5 space-y-2 border-l-2 border-border pl-3">
              {data.evidence.slice(0, 6).map((entry, index) => (
                <EvidenceItem key={index} entry={entry} />
              ))}
            </ul>
          </div>
        ) : null}

        <div className="border-t border-border pt-3">
          <h4 className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
            Assumptions
          </h4>
          <ul className="mt-1.5 space-y-0.5 text-xs text-fg-muted">
            <li>
              ICP:{" "}
              {assumptions.icp ? (
                <a href="/icp" className="text-accent underline-offset-2 hover:underline">
                  {assumptions.icp.name}
                </a>
              ) : (
                "none active — ICP fit could not be judged"
              )}
            </li>
            <li>
              Selected markets:{" "}
              {assumptions.selected_markets.length
                ? assumptions.selected_markets.join(", ")
                : "none chosen yet"}
            </li>
          </ul>
        </div>
      </div>

      <div>
        <h4 className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
          How it adds up
        </h4>
        <ul className="mt-1 divide-y divide-border/60">
          {data.components.map((component) => (
            <ComponentRow key={component.component} component={component} />
          ))}
        </ul>
      </div>
    </div>
  );
}
