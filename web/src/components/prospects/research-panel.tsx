"use client";

import { AlertTriangle, ExternalLink, Quote, Sparkles } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ProspectResearch, SignalEvidence } from "@/lib/api/types";
import { useProspectResearch } from "@/lib/hooks/use-prospects";

/**
 * The sales brief (PRD section 34) and the reason to contact (section 35).
 *
 * The reason leads, in the largest type on the panel, because it is the one
 * sentence a rep will actually use and the build plan calls it the
 * highest-leverage string in the product.
 *
 * **Its evidence sits directly underneath it, not behind a disclosure.** The
 * rule in section 35 is that the explanation must be evidence-based, and the
 * server enforces that by refusing to store a reason whose quote it cannot
 * find in the source material. The interface's job is the other half: making
 * the quote impossible to miss, so the person about to repeat the claim to a
 * buyer reads what it rests on first.
 *
 * **A rejected reason says so.** When the agent wrote one that failed
 * verification, the panel reports that rather than showing an empty space —
 * "nothing to say yet" and "we threw away what it wrote" call for different
 * responses, and an empty space is indistinguishable from either.
 */

function EvidenceLine({ entry }: { entry: SignalEvidence }) {
  return (
    <li className="text-xs text-fg-muted">
      {entry.quote ? (
        <p className="flex items-start gap-1.5">
          <Quote aria-hidden className="mt-0.5 size-3 shrink-0 text-fg-subtle" />
          <em>&ldquo;{entry.quote}&rdquo;</em>
        </p>
      ) : (
        <p>{entry.claim}</p>
      )}
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
        {title}
      </h4>
      <div className="mt-1 text-sm text-fg-muted">{children}</div>
    </div>
  );
}

function Brief({ research }: { research: ProspectResearch }) {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        {research.has_reason ? (
          <div>
            <h4 className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
              Why contact them
            </h4>
            <p className="mt-1 text-sm font-medium text-fg">{research.reason_sentence}</p>
            <ul className="mt-2 space-y-1.5 border-l-2 border-accent/40 pl-3">
              {research.reason_evidence.map((entry, index) => (
                <EvidenceLine key={index} entry={entry} />
              ))}
            </ul>
            {research.reason_confidence ? (
              <p className="mt-1 text-xs text-fg-subtle">
                {research.reason_confidence} confidence
              </p>
            ) : null}
          </div>
        ) : research.reason_rejected ? (
          <p className="flex items-start gap-1.5 text-xs text-signal-warm">
            <AlertTriangle aria-hidden className="mt-0.5 size-3 shrink-0" />
            {/* Said out loud. The agent produced a reason and it was
                discarded; that is worth knowing, because it means asking
                again is unlikely to help until there is more evidence. */}
            No reason to contact was kept: {research.reason_rejected}
          </p>
        ) : null}

        {research.summary ? <Section title="Summary">{research.summary}</Section> : null}

        {research.why_they_may_buy.length ? (
          <Section title="Why they may buy">
            <ul className="list-disc space-y-0.5 pl-4">
              {research.why_they_may_buy.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </Section>
        ) : null}

        {research.likely_pain.length ? (
          <Section title="Likely pain">
            <ul className="list-disc space-y-0.5 pl-4">
              {research.likely_pain.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </Section>
        ) : null}
      </div>

      <div className="space-y-4">
        {research.suggested_approach ? (
          <Section title="Suggested approach">{research.suggested_approach}</Section>
        ) : null}

        {research.possible_use_case ? (
          <Section title="Possible use case">{research.possible_use_case}</Section>
        ) : null}

        {research.personalization_points.length ? (
          <Section title="Personalization">
            <ul className="space-y-2">
              {research.personalization_points.map((point, index) => (
                <li key={index}>
                  <p className="text-sm text-fg">{point.point}</p>
                  {point.source_quote ? (
                    // Every point carries the excerpt it was taken from: the
                    // server discards any that do not, because these go
                    // straight into the message.
                    <p className="text-xs italic text-fg-subtle">
                      &ldquo;{point.source_quote}&rdquo;
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </Section>
        ) : null}

        {research.decision_maker_titles.length ? (
          <Section title="Who to reach">
            {research.decision_maker_titles.join(", ")}
          </Section>
        ) : null}

        {research.unknowns.length ? (
          <Section title="Not known">
            <ul className="list-disc space-y-0.5 pl-4 text-xs">
              {research.unknowns.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </Section>
        ) : null}

        <p className="text-xs text-fg-subtle">
          {research.source_signal_count} signal
          {research.source_signal_count === 1 ? "" : "s"} in view
          {research.researched_at
            ? ` · researched ${new Date(research.researched_at).toLocaleDateString()}`
            : null}
          {research.edited_fields.length
            ? ` · ${research.edited_fields.length} field(s) edited by hand`
            : null}
        </p>
      </div>
    </div>
  );
}

export function ResearchPanel({
  prospectId,
  canManage,
}: {
  prospectId: string;
  canManage: boolean;
}) {
  const { research, isLoading, request } = useProspectResearch(prospectId);

  if (isLoading) {
    return <p className="text-sm text-fg-subtle">Loading the brief…</p>;
  }

  if (!research) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-fg-subtle">
          No brief yet. Research reads the signals, the record and the site, and writes
          the reason to contact with the evidence behind it.
        </p>
        {canManage ? (
          <Button
            size="sm"
            variant="secondary"
            loading={request.isPending}
            onClick={() => request.mutate()}
          >
            <Sparkles aria-hidden className="size-3.5" />
            {request.isSuccess ? "Queued" : "Research this prospect"}
          </Button>
        ) : null}
      </div>
    );
  }

  if (research.status === "failed") {
    return (
      <p className="text-sm text-fg-subtle">
        The research did not complete: {research.research_error}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <Brief research={research} />
      {canManage ? (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            loading={request.isPending}
            onClick={() => request.mutate()}
          >
            <Sparkles aria-hidden className="size-3.5" />
            Research again
          </Button>
          {research.edited_fields.length ? (
            <Badge tone="neutral">Your edits are kept across re-runs</Badge>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
