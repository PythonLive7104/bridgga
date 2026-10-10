"use client";

import {
  AlertTriangle,
  ArrowRight,
  Check,
  Globe2,
  Loader2,
  Sparkles,
} from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { CompanyProfile, ICP, MarketRecommendation } from "@/lib/api/types";
import { useCompanyProfile } from "@/lib/hooks/use-company-profile";
import { useICPs } from "@/lib/hooks/use-icp";
import { useMarkets } from "@/lib/hooks/use-markets";
import { cn } from "@/lib/utils";

/**
 * The five onboarding steps that exist today (PRD section 25, steps 1-5).
 *
 * Steps 6 to 9 — channels, prospects, campaign, launch — need mailboxes and
 * campaigns, which are Phase 3.
 *
 * Two things run through all of them.
 *
 * **Nothing is spent without a click.** Analysis crawls several pages and
 * makes an advanced-tier model call; the ICP and the market ranking are model
 * calls too. Each is a button with the reason beside it, never something that
 * happens because a screen loaded. It is the customer's money and their
 * first impression of what this product does with it.
 *
 * **Every step can be skipped.** A wizard that will not let go is one people
 * learn to dread, and the work survives: the profile, the ICP and the markets
 * are all editable later from their own pages.
 */

export function StepShell({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{title}</h1>
        <p className="mt-1 text-sm text-fg-muted">{description}</p>
      </header>
      {children}
      {footer ? <div className="flex flex-wrap items-center gap-3">{footer}</div> : null}
    </div>
  );
}

/* --------------------------------------------------------------- analysis */

export function AnalysisStep({ onSkip }: { onSkip: () => void }) {
  const { profile, isAnalyzing, analyze } = useCompanyProfile();
  const failed = profile?.status === "failed";

  return (
    <StepShell
      title="Read my website"
      description="Bridgga reads your homepage and a few key pages, then describes the business behind them. Everything it concludes is editable on the next screen."
    >
      <Card>
        <CardContent className="space-y-3 p-5">
          <p className="flex items-center gap-2 text-sm text-fg">
            <Globe2 aria-hidden className="size-4 text-accent" />
            {profile?.website || "No website on file"}
          </p>

          {isAnalyzing ? (
            <p className="flex items-center gap-2 text-sm text-fg-muted">
              <Loader2 aria-hidden className="size-4 animate-spin" />
              Reading the site. This takes up to a minute — it fetches several pages and
              reads them properly.
            </p>
          ) : null}

          {failed ? (
            <p className="flex items-start gap-2 text-sm text-signal-warm">
              <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
              {/* The reason, not a generic failure: a refused fetch and an
                  unreachable host call for different things from the reader. */}
              {profile?.analysis_error || "The site could not be read."}
            </p>
          ) : null}

          {/* Stated before it is spent, every time. */}
          <p className="text-xs text-fg-subtle">
            Uses credits. It is the one call everything downstream is built on, so it runs
            on the strongest model.
          </p>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => analyze.mutate(undefined)} loading={isAnalyzing}>
          <Sparkles aria-hidden className="size-4" />
          {failed ? "Try again" : "Read my website"}
        </Button>
        <Button variant="ghost" onClick={onSkip}>
          Skip for now
        </Button>
      </div>
    </StepShell>
  );
}

/* ---------------------------------------------------------------- confirm */

/** The five things section 25 step 3 asks a customer to confirm. */
const CONFIRM_FIELDS: {
  key: keyof CompanyProfile;
  label: string;
  hint: string;
  list?: boolean;
}[] = [
  { key: "products", label: "Product", hint: "What you sell", list: true },
  { key: "industry", label: "Industry", hint: "The business you are in" },
  {
    key: "target_customers",
    label: "Target market",
    hint: "The kinds of organisation you serve",
    list: true,
  },
  { key: "pricing_summary", label: "Pricing", hint: "Blank if you do not publish it" },
  { key: "business_model", label: "Business model", hint: "How you make money" },
];

export function ConfirmStep({ onSkip }: { onSkip: () => void }) {
  const { profile, save, confirm } = useCompanyProfile();
  const [draft, setDraft] = React.useState<Record<string, string>>({});

  if (!profile) return null;

  const valueOf = (key: keyof CompanyProfile, list?: boolean): string => {
    if (draft[key] !== undefined) return draft[key];
    const value = profile[key];
    return list && Array.isArray(value) ? value.join(", ") : String(value ?? "");
  };

  const edited = Object.keys(draft).length > 0;

  async function saveAndConfirm() {
    if (edited) {
      const changes: Record<string, unknown> = {};
      for (const field of CONFIRM_FIELDS) {
        const value = draft[field.key];
        if (value === undefined) continue;
        changes[field.key] = field.list
          ? value
              .split(",")
              .map((part) => part.trim())
              .filter(Boolean)
          : value;
      }
      await save.mutateAsync(changes);
    }
    await confirm.mutateAsync();
  }

  return (
    <StepShell
      title="Does this describe your business?"
      description="This is what the site said. Correct anything that is wrong — your version is kept, and re-reading the site later will not overwrite it."
    >
      <Card>
        <CardContent className="space-y-4 p-5">
          {CONFIRM_FIELDS.map((field) => (
            <div key={field.key}>
              <Input
                label={field.label}
                value={valueOf(field.key, field.list)}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, [field.key]: event.target.value }))
                }
                placeholder={field.hint}
              />
              {/* An empty field is a finding, not a gap to fill in. The site
                  publishing no pricing is worth knowing. */}
              {!valueOf(field.key, field.list) ? (
                <p className="mt-1 text-xs text-fg-subtle">
                  The site did not say. Leave it blank if that is right.
                </p>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={saveAndConfirm} loading={save.isPending || confirm.isPending}>
          <Check aria-hidden className="size-4" />
          {edited ? "Save and confirm" : "This is right"}
        </Button>
        <Button variant="ghost" onClick={onSkip}>
          Skip for now
        </Button>
      </div>
    </StepShell>
  );
}

/* -------------------------------------------------------------------- icp */

function IcpSummary({ icp }: { icp: ICP }) {
  const rows: [string, string][] = [
    ["Industries", icp.industries.join(", ")],
    ["Countries", icp.countries.join(", ")],
    ["Size", icp.employee_range || icp.business_size],
    ["Buyer", icp.job_titles.join(", ")],
  ];

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <p className="text-sm font-medium text-fg">{icp.name}</p>
        <dl className="grid gap-2 sm:grid-cols-2">
          {rows
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs uppercase tracking-wide text-fg-subtle">
                  {label}
                </dt>
                <dd className="text-sm text-fg-muted">{value}</dd>
              </div>
            ))}
        </dl>
        {icp.pain_signals.length ? (
          <div>
            <p className="text-xs uppercase tracking-wide text-fg-subtle">Watches for</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {/* The closed vocabulary is the point: each of these is
                  something the signal engine actually detects. */}
              {icp.pain_signals.map((signal, index) => (
                <Badge key={index} tone="accent">
                  {signal.type.replace(/_/g, " ")}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}
        {icp.rationale ? <p className="text-sm text-fg-muted">{icp.rationale}</p> : null}
      </CardContent>
    </Card>
  );
}

export function IcpStep({ onSkip }: { onSkip: () => void }) {
  const { icps, active, generate, activate } = useICPs();
  const draft = active ?? icps[0] ?? null;

  return (
    <StepShell
      title="Who should you be selling to?"
      description="Drawn from what your site says you do. Edit it any time on the ICP page — it decides which companies the product goes looking for."
    >
      {draft ? <IcpSummary icp={draft} /> : null}

      <div className="flex flex-wrap items-center gap-3">
        {draft && !draft.is_active ? (
          <Button onClick={() => activate.mutate(draft.id)} loading={activate.isPending}>
            <Check aria-hidden className="size-4" />
            Use this profile
          </Button>
        ) : (
          <Button onClick={() => generate.mutate()} loading={generate.isPending}>
            <Sparkles aria-hidden className="size-4" />
            {draft ? "Draft another" : "Draft my ideal customer"}
          </Button>
        )}
        <Button variant="ghost" onClick={onSkip}>
          Skip for now
        </Button>
      </div>
      {!draft ? <p className="text-xs text-fg-subtle">Uses credits.</p> : null}
    </StepShell>
  );
}

/* ---------------------------------------------------------------- markets */

function MarketRow({
  market,
  selected,
  onToggle,
}: {
  market: MarketRecommendation;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={selected}
        className={cn(
          "w-full rounded-[var(--radius-card)] border p-3 text-left transition-colors",
          selected
            ? "border-accent bg-accent-subtle"
            : "border-border hover:border-border-strong",
        )}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-fg">{market.country.name}</span>
          <Badge
            tone={market.fit === "high" ? "hot" : market.fit === "low" ? "cold" : "warm"}
          >
            {market.fit.replace("_", " ")}
          </Badge>
          <span className="tabular ml-auto text-xs text-fg-subtle">{market.score}</span>
        </div>
        {/* The reasoning, never just the number: section 28 requires each
            recommendation to explain itself, and a score nobody can argue
            with is a score nobody can check. */}
        <p className="mt-1 line-clamp-2 text-xs text-fg-muted">{market.reasoning}</p>
      </button>
    </li>
  );
}

export function MarketsStep({ onFinish }: { onFinish: () => void }) {
  const { markets, selected, recommend, select } = useMarkets();
  const [chosen, setChosen] = React.useState<string[] | null>(null);
  const codes = chosen ?? selected.map((market) => market.country.code);

  const toggle = (code: string) =>
    setChosen(
      codes.includes(code) ? codes.filter((item) => item !== code) : [...codes, code],
    );

  return (
    <StepShell
      title="Where should you sell?"
      description="Ranked for your business against what is known about each market. Pick the ones you want to work — prospect search uses them."
    >
      {markets.length ? (
        <ul className="grid gap-2 sm:grid-cols-2">
          {markets.slice(0, 8).map((market) => (
            <MarketRow
              key={market.id}
              market={market}
              selected={codes.includes(market.country.code)}
              onToggle={() => toggle(market.country.code)}
            />
          ))}
        </ul>
      ) : (
        <Card>
          <CardContent className="space-y-2 p-5">
            <p className="text-sm text-fg-muted">
              Rank the ten launch markets for what you sell. Uses credits.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {markets.length ? (
          <Button
            onClick={async () => {
              if (codes.length) await select.mutateAsync(codes);
              onFinish();
            }}
            loading={select.isPending}
            disabled={!codes.length}
          >
            <Check aria-hidden className="size-4" />
            Use {codes.length} market{codes.length === 1 ? "" : "s"}
          </Button>
        ) : (
          <Button onClick={() => recommend.mutate(false)} loading={recommend.isPending}>
            <Sparkles aria-hidden className="size-4" />
            Rank my markets
          </Button>
        )}
        <Button variant="ghost" onClick={onFinish}>
          {markets.length ? "Finish without choosing" : "Skip for now"}
          <ArrowRight aria-hidden className="size-4" />
        </Button>
      </div>
    </StepShell>
  );
}
