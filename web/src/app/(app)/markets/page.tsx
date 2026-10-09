"use client";

import { AlertTriangle, Check, Globe2, Sparkles } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import type { MarketFit, MarketRecommendation } from "@/lib/api/types";
import { useMarkets } from "@/lib/hooks/use-markets";
import { useSession } from "@/lib/hooks/use-session";
import { cn } from "@/lib/utils";

/**
 * Market recommendations (PRD section 28).
 *
 * Every card leads with the reasoning, not the score. Section 28 requires each
 * recommendation to explain itself, and a page that shows "Nigeria 92" with
 * the explanation folded away has met the letter of that and none of its
 * point: a number nobody can argue with is a number nobody can check.
 *
 * Ranking and selection are kept visibly separate, because they are different
 * claims. The ranking is what the agent thinks; the selection is what the
 * customer decided, and it is the selection that prospect discovery reads.
 */

const FIT_STYLES: Record<MarketFit, string> = {
  high: "bg-signal-hot/15 text-signal-hot",
  medium_high: "bg-signal-warm/15 text-signal-warm",
  medium: "bg-bg-subtle text-fg-muted",
  low: "bg-bg-subtle text-fg-subtle",
};

/** The section 28 factors, in the order that section lists them. */
const FACTOR_LABELS: Record<string, string> = {
  product_fit: "Product fit",
  company_density: "Company density",
  industry_density: "Industry density",
  estimated_demand: "Estimated demand",
  competition: "Competition",
  communication: "Communication",
  regulatory: "Regulatory",
  language: "Language",
  purchasing_power: "Purchasing power",
};

function MarketCard({
  market,
  canManage,
  onToggle,
  busy,
}: {
  market: MarketRecommendation;
  canManage: boolean;
  onToggle: () => void;
  busy: boolean;
}) {
  const factors = Object.entries(market.factors).filter(([, verdict]) => verdict);

  return (
    <Card className={cn(market.is_selected && "border-accent")}>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-fg">{market.country.name}</h3>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  FIT_STYLES[market.fit],
                )}
              >
                {market.fit_label}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-fg-subtle">
              {market.country.currency}
              {market.country.languages.length
                ? ` · ${market.country.languages.join(", ")}`
                : null}
              {market.country.business_hubs.length
                ? ` · ${market.country.business_hubs.slice(0, 3).join(", ")}`
                : null}
            </p>
          </div>

          {canManage ? (
            <Button
              size="sm"
              variant={market.is_selected ? "primary" : "secondary"}
              onClick={onToggle}
              disabled={busy}
              aria-pressed={market.is_selected}
            >
              {market.is_selected ? (
                <>
                  <Check aria-hidden className="size-3.5" />
                  Selected
                </>
              ) : (
                "Select this market"
              )}
            </Button>
          ) : null}
        </div>

        {/* The reasoning, not folded away. It is the requirement. */}
        <p className="text-sm leading-relaxed text-fg-muted">{market.reasoning}</p>

        {factors.length ? (
          <dl className="grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
            {factors.map(([key, verdict]) => (
              <div key={key} className="flex gap-2">
                <dt className="shrink-0 text-fg-subtle">
                  {FACTOR_LABELS[key] ?? key.replace(/_/g, " ")}:
                </dt>
                <dd className="text-fg-muted">{verdict}</dd>
              </div>
            ))}
          </dl>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 border-t border-border/70 pt-3">
          {market.recommended_channels.map((channel) => (
            <span
              key={channel}
              className="rounded-md border border-border px-2 py-0.5 text-xs capitalize text-fg-muted"
            >
              {channel}
            </span>
          ))}
          {market.country.data_protection_law ? (
            <span className="ml-auto text-xs text-fg-subtle">
              {market.country.data_protection_law}
            </span>
          ) : null}
        </div>

        {market.cautions.length ? (
          <ul className="space-y-1">
            {market.cautions.map((caution) => (
              <li
                key={caution}
                className="flex items-start gap-2 text-xs text-signal-warm"
              >
                <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                {caution}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function MarketsPage() {
  const { can } = useSession();
  const { markets, selected, isLoading, recommend, select } = useMarkets();
  const [international, setInternational] = React.useState(false);

  const canManage = can("icp.manage");

  function toggle(code: string) {
    const codes = new Set(selected.map((market) => market.country.code));
    if (codes.has(code)) codes.delete(code);
    else codes.add(code);
    select.mutate([...codes]);
  }

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy>
        <div className="h-8 w-56 animate-pulse rounded bg-bg-subtle" />
        <div className="h-64 animate-pulse rounded-[var(--radius-card)] bg-bg-subtle" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-fg">Markets</h1>
          <p className="mt-1 max-w-2xl text-sm text-fg-muted">
            Where to sell, ranked for your business, with the reasoning behind each one.
            Choosing a market is what targets your prospect searches.
          </p>
        </div>
        {canManage ? (
          <Button
            onClick={() => recommend.mutate(international)}
            loading={recommend.isPending}
          >
            <Sparkles aria-hidden className="size-4" />
            {markets.length ? "Re-rank markets" : "Recommend markets"}
          </Button>
        ) : null}
      </header>

      {recommend.isError ? (
        <p
          role="alert"
          className="rounded-[var(--radius-control)] bg-negative/10 px-3 py-2 text-sm text-negative"
        >
          {(recommend.error as Error).message}
        </p>
      ) : null}

      {canManage ? (
        <label className="flex items-center gap-2 text-sm text-fg-muted">
          <input
            type="checkbox"
            checked={international}
            onChange={(event) => setInternational(event.target.checked)}
            className="size-4 rounded border-border accent-[var(--accent)]"
          />
          {/* PRD section 6.2: the reverse flow, selling out of Africa as well
              as into it. */}
          Include markets outside Africa
        </label>
      ) : null}

      {markets.length === 0 ? (
        <EmptyState
          title="No markets ranked yet"
          description="We rank countries against your company and your ICP, using what we know about each one: currency, languages, reachable channels and the data protection law that applies. Confirm your company and create an ICP first."
          action={
            canManage ? (
              <Button
                onClick={() => recommend.mutate(international)}
                loading={recommend.isPending}
              >
                <Globe2 aria-hidden className="size-4" />
                Recommend markets
              </Button>
            ) : null
          }
        />
      ) : (
        <>
          {selected.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Working these markets</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-fg-muted">
                  {selected.map((market) => market.country.name).join(", ")}. Prospect
                  searches and campaigns will target these.
                </p>
              </CardContent>
            </Card>
          ) : null}

          <div className="grid gap-4 xl:grid-cols-2">
            {markets.map((market) => (
              <MarketCard
                key={market.id}
                market={market}
                canManage={canManage}
                busy={select.isPending}
                onToggle={() => toggle(market.country.code)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
