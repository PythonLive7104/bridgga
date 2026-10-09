"use client";

import { Clock, ExternalLink, Quote, Radar, X } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import type { LeadSignal } from "@/lib/api/types";
import {
  useDismissSignal,
  useSignalSummary,
  useSignals,
  type SignalQuery,
} from "@/lib/hooks/use-signals";
import { useSession } from "@/lib/hooks/use-session";
import { cn } from "@/lib/utils";

/**
 * The buying-signal feed (PRD section 33).
 *
 * Three decisions, each of them the opposite of what a dashboard usually does.
 *
 * **The evidence is on the card, not behind it.** Section 58 makes the
 * evidence the product. A rep is about to put this signal in front of a real
 * buyer, so the quote and the link have to be readable before they do, not
 * one click away in a drawer nobody opens.
 *
 * **Age is stated, not implied.** Every signal shows how old it is and when
 * it stops counting. A feed that shows "Hiring" with no date invites somebody
 * to open a conversation about a role that was filled two months ago.
 *
 * **Dismissing is a first-class action.** The detectors will be wrong, and the
 * only thing worse than a wrong signal is a wrong signal nobody can get rid
 * of. It is kept rather than deleted, so the mistake stays visible to us.
 */

const DAYS_OPTIONS = [
  { label: "All", value: 0 },
  { label: "Last 7 days", value: 7 },
  { label: "Last 30 days", value: 30 },
];

function label(signalType: string): string {
  return signalType.replace(/_/g, " ").replace(/^./, (char) => char.toUpperCase());
}

function ageText(signal: LeadSignal): string {
  if (signal.age_days <= 0) return "today";
  if (signal.age_days === 1) return "yesterday";
  if (signal.age_days < 30) return `${signal.age_days} days ago`;
  const months = Math.floor(signal.age_days / 30);
  return months === 1 ? "last month" : `${months} months ago`;
}

function expiryText(signal: LeadSignal): string {
  const days = Math.ceil(
    (new Date(signal.expires_at).getTime() - Date.now()) / 86_400_000,
  );
  if (days <= 0) return "no longer counted";
  if (days === 1) return "stops counting tomorrow";
  return `stops counting in ${days} days`;
}

/** Strength drives the band, and the number is always shown beside it. */
function strengthTone(value: number): "hot" | "warm" | "cold" {
  if (value >= 70) return "hot";
  if (value >= 45) return "warm";
  return "cold";
}

function EvidenceList({ signal }: { signal: LeadSignal }) {
  const entries = signal.evidence.filter((item) => item.quote || item.claim);
  if (!entries.length) return null;

  return (
    <ul className="mt-3 space-y-2 border-l-2 border-border pl-3">
      {entries.slice(0, 3).map((item, index) => (
        <li key={index} className="text-xs text-fg-muted">
          {item.quote ? (
            <p className="flex gap-1.5">
              <Quote aria-hidden className="mt-0.5 size-3 shrink-0 text-fg-subtle" />
              <span className="italic">&ldquo;{item.quote}&rdquo;</span>
            </p>
          ) : (
            <p>{item.claim}</p>
          )}
          {item.source_url ? (
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="mt-0.5 inline-flex items-center gap-1 text-accent underline-offset-2 hover:underline"
            >
              {item.source_type.replace(/_/g, " ") || "source"}
              <ExternalLink aria-hidden className="size-3" />
            </a>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function SignalCard({
  signal,
  canManage,
  onDismiss,
  dismissing,
}: {
  signal: LeadSignal;
  canManage: boolean;
  onDismiss: (signal: LeadSignal) => void;
  dismissing: boolean;
}) {
  return (
    <Card className={cn(signal.is_dismissed && "opacity-60")}>
      <CardContent className="space-y-2 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="accent">
                <Radar aria-hidden className="size-3" />
                {label(signal.signal_type)}
              </Badge>
              <Badge tone={strengthTone(signal.decayed_strength)} className="tabular">
                <span className="sr-only">Signal strength </span>
                {signal.decayed_strength}
                <span className="opacity-70">/100</span>
              </Badge>
              {signal.confidence ? (
                <span className="text-xs text-fg-subtle">
                  {signal.confidence} confidence
                </span>
              ) : null}
            </div>

            <h2 className="mt-2 truncate text-sm font-medium text-fg">{signal.title}</h2>
            <p className="text-xs text-fg-subtle">
              {signal.company_name}
              {signal.company_domain ? ` · ${signal.company_domain}` : null}
            </p>
          </div>

          {canManage && !signal.is_dismissed ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDismiss(signal)}
              loading={dismissing}
              aria-label={`Dismiss: ${signal.title}`}
            >
              <X aria-hidden className="size-3.5" />
              Not relevant
            </Button>
          ) : null}
        </div>

        {signal.description ? (
          <p className="text-sm text-fg-muted">{signal.description}</p>
        ) : null}

        <EvidenceList signal={signal} />

        <p className="flex flex-wrap items-center gap-1.5 text-xs text-fg-subtle">
          <Clock aria-hidden className="size-3" />
          {/* Both halves of the staleness story: how old it is, and when it
              stops counting. Section 33 requires the expiry; a date on its
              own does not tell a rep whether this is still worth mentioning. */}
          {ageText(signal)} · {expiryText(signal)}
          {signal.detector ? ` · found by ${signal.detector.replace(/_/g, " ")}` : null}
          {signal.is_dismissed ? " · dismissed" : null}
        </p>
      </CardContent>
    </Card>
  );
}

export default function SignalsPage() {
  const { can } = useSession();
  const [query, setQuery] = React.useState<SignalQuery>({});
  const { signals, total, isLoading } = useSignals(query);
  const summary = useSignalSummary();
  const dismiss = useDismissSignal();

  const canManage = can("prospect.manage");
  const selected = query.type ?? [];

  const toggleType = (value: string) =>
    setQuery((current) => {
      const existing = current.type ?? [];
      const next = existing.includes(value)
        ? existing.filter((item) => item !== value)
        : [...existing, value];
      return { ...current, type: next.length ? next : undefined };
    });

  const handleDismiss = (signal: LeadSignal) => {
    const reason = window.prompt(
      `Why is this not relevant? (optional)\n\n${signal.title}`,
      "",
    );
    // A null return means the person cancelled; an empty string means they
    // dismissed it without giving a reason, which is allowed.
    if (reason === null) return;
    dismiss.mutate({ id: signal.id, reason });
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">Buying signals</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Things that happened at companies you are watching, each with the evidence
          behind it and a date it stops counting.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        {(summary.data?.types ?? []).map((item) => {
          const active = selected.includes(item.value);
          return (
            <button
              key={item.value}
              type="button"
              onClick={() => toggleType(item.value)}
              aria-pressed={active}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs transition-colors",
                active
                  ? "border-accent bg-accent text-accent-fg"
                  : "border-border text-fg-muted hover:border-border-strong",
              )}
            >
              {label(item.value)}
              <span className={cn("ml-1", active ? "opacity-80" : "text-fg-subtle")}>
                {item.count}
              </span>
            </button>
          );
        })}

        <span className="ml-auto flex items-center gap-2">
          {DAYS_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() =>
                setQuery((current) => ({ ...current, days: option.value || undefined }))
              }
              aria-pressed={(query.days ?? 0) === option.value}
              className={cn(
                "text-xs underline-offset-2 hover:underline",
                (query.days ?? 0) === option.value ? "text-fg" : "text-fg-subtle",
              )}
            >
              {option.label}
            </button>
          ))}
        </span>
      </div>

      <p className="text-sm text-fg-subtle" aria-live="polite">
        {isLoading ? "Loading…" : `${total} live signal${total === 1 ? "" : "s"}`}
      </p>

      {!isLoading && !signals.length ? (
        <EmptyState
          title="No live signals"
          description={
            "Nothing is happening at your prospects that the detectors can see — or " +
            "nothing has been crawled twice yet. A signal needs a before and an after."
          }
          action={
            selected.length || query.days ? (
              <Button variant="secondary" onClick={() => setQuery({})}>
                Clear filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-3">
          {signals.map((signal) => (
            <SignalCard
              key={signal.id}
              signal={signal}
              canManage={canManage}
              onDismiss={handleDismiss}
              dismissing={dismiss.isPending && dismiss.variables?.id === signal.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
