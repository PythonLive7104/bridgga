"use client";

import { AlertTriangle, Globe, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import * as React from "react";

import {
  EditableList,
  EditableText,
  EvidenceRow,
} from "@/components/intelligence/editable-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { CompanyProfileField } from "@/lib/api/types";
import { useCompanyProfile } from "@/lib/hooks/use-company-profile";
import { useSession } from "@/lib/hooks/use-session";

/**
 * The company profile (PRD section 26), and onboarding step 3 (section 25).
 *
 * Every field the agent writes is editable here, and each one carries its own
 * provenance: whether a human changed it, and what the agent originally said.
 * That is not decoration. Re-analysis preserves edited fields, so the customer
 * needs to see which fields they have pinned and be able to let one go again.
 *
 * Two deliberate refusals:
 *
 * * An empty field is never hidden. For pricing in particular, blank is a
 *   finding -- "this site publishes no prices" -- and hiding it would make a
 *   conclusion look like a missing feature.
 * * Nothing here is presented as fact without its source. The evidence panel
 *   is the product's actual claim to be trusted (section 58).
 */

const TEXT_FIELDS: {
  field: CompanyProfileField;
  label: string;
  multiline?: boolean;
  emptyHint?: string;
}[] = [
  { field: "company_name", label: "Company name" },
  { field: "one_line_summary", label: "In one line", multiline: true },
  { field: "industry", label: "Industry" },
  { field: "business_model", label: "Business model" },
  { field: "value_proposition", label: "Value proposition", multiline: true },
  {
    field: "pricing_summary",
    label: "Pricing",
    multiline: true,
    emptyHint: "The website publishes no pricing. That is a finding, not a gap.",
  },
];

const LIST_FIELDS: { field: CompanyProfileField; label: string; emptyHint?: string }[] = [
  { field: "products", label: "Products" },
  { field: "target_customers", label: "Target customers" },
  { field: "use_cases", label: "Use cases" },
  { field: "pain_points_solved", label: "Pain points solved" },
  { field: "geographies", label: "Geographies" },
  { field: "buyer_personas", label: "Buyer personas" },
  {
    field: "competitors",
    label: "Competitors",
    emptyHint:
      "The website names no competitors. We do not add any from general knowledge.",
  },
];

export default function CompanyProfilePage() {
  const { can } = useSession();
  const { profile, isLoading, isAnalyzing, analyze, save, reset, confirm } =
    useCompanyProfile();
  const [website, setWebsite] = React.useState("");

  const canManage = can("company_profile.manage");

  React.useEffect(() => {
    if (profile?.website) setWebsite(profile.website);
  }, [profile?.website]);

  if (isLoading || !profile) {
    return (
      <div className="space-y-4" aria-busy>
        <div className="h-8 w-64 animate-pulse rounded bg-bg-subtle" />
        <div className="h-64 animate-pulse rounded-[var(--radius-card)] bg-bg-subtle" />
      </div>
    );
  }

  const editedCount = profile.edited_fields.length;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-fg">Your company</h1>
          <p className="mt-1 max-w-2xl text-sm text-fg-muted">
            What we understood from your website. Everything here is editable, and your
            edits survive the next analysis.
          </p>
        </div>
        {profile.status === "confirmed" ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-positive/15 px-3 py-1 text-sm text-positive">
            <ShieldCheck aria-hidden className="size-4" />
            Confirmed
          </span>
        ) : null}
      </header>

      {/* Analysis control */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Globe aria-hidden className="size-4 text-fg-subtle" />
            Website
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1">
              <Input
                label="Address we read"
                value={website}
                onChange={(event) => setWebsite(event.target.value)}
                placeholder="yourcompany.com"
                disabled={!canManage || isAnalyzing}
              />
            </div>
            <Button
              onClick={() => analyze.mutate(website)}
              disabled={!canManage || isAnalyzing || !website}
              loading={isAnalyzing}
            >
              <RefreshCw aria-hidden className="size-4" />
              {profile.last_analyzed_at ? "Re-analyse" : "Analyse"}
            </Button>
          </div>

          {isAnalyzing ? (
            <p
              // Announced politely: the result arrives by polling, so a screen
              // reader user would otherwise have no idea work is in progress.
              role="status"
              className="flex items-center gap-2 text-sm text-fg-muted"
            >
              <Loader2 aria-hidden className="size-4 animate-spin" />
              Reading your website and the pages it links to. This takes a moment.
            </p>
          ) : null}

          {profile.status === "failed" && profile.analysis_error ? (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-[var(--radius-control)] bg-negative/10 p-3 text-sm text-negative"
            >
              <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
              {profile.analysis_error}
            </p>
          ) : null}

          {profile.last_analyzed_at ? (
            <p className="text-xs text-fg-subtle">
              Last analysed{" "}
              <time dateTime={profile.last_analyzed_at}>
                {new Date(profile.last_analyzed_at).toLocaleString()}
              </time>
              {profile.prompt_pin ? ` · ${profile.prompt_pin}` : null}
              {editedCount
                ? ` · ${editedCount} field${editedCount === 1 ? "" : "s"} you edited`
                : null}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>The business</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {TEXT_FIELDS.map(({ field, label, multiline, emptyHint }) => (
                <EditableText
                  key={field}
                  label={label}
                  value={profile[field] as string}
                  meta={profile.fields_meta[field]}
                  multiline={multiline}
                  emptyHint={emptyHint}
                  readOnly={!canManage}
                  isSaving={save.isPending}
                  onSave={(value) => save.mutate({ [field]: value })}
                  onRevert={() => reset.mutate([field])}
                />
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Market and offering</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {LIST_FIELDS.map(({ field, label, emptyHint }) => (
                <EditableList
                  key={field}
                  label={label}
                  value={profile[field] as string[]}
                  meta={profile.fields_meta[field]}
                  emptyHint={emptyHint}
                  readOnly={!canManage}
                  isSaving={save.isPending}
                  onSave={(value) => save.mutate({ [field]: value })}
                  onRevert={() => reset.mutate([field])}
                />
              ))}
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Evidence</CardTitle>
            </CardHeader>
            <CardContent>
              {profile.evidence.length ? (
                <ul className="space-y-1">
                  {profile.evidence.map((item, index) => (
                    <EvidenceRow
                      key={`${item.claim}-${index}`}
                      claim={item.claim}
                      quote={item.quote}
                      sourceUrl={item.source_url}
                      confidence={item.confidence}
                    />
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-fg-subtle">
                  Nothing yet. Every claim above will arrive with the page it came from.
                </p>
              )}
            </CardContent>
          </Card>

          {profile.unknowns.length ? (
            <Card>
              <CardHeader>
                <CardTitle>What the site did not say</CardTitle>
              </CardHeader>
              <CardContent>
                {/* Shown as prominently as the findings: a gap the customer can
                    fill in is worth more than a guess we could have made. */}
                <ul className="space-y-2 text-sm text-fg-muted">
                  {profile.unknowns.map((item) => (
                    <li key={item} className="flex gap-2">
                      <span aria-hidden className="text-fg-subtle">
                        —
                      </span>
                      {item}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}

          {profile.sources.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Pages read</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  {profile.sources.map((source) => (
                    <li key={source.id} className="truncate">
                      <a
                        href={source.final_url || source.requested_url}
                        rel="noopener noreferrer nofollow"
                        target="_blank"
                        className="text-fg-muted underline underline-offset-2 hover:text-fg"
                      >
                        {source.title || source.final_url || source.requested_url}
                      </a>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </aside>
      </div>

      {profile.status === "ready" && canManage ? (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-4 py-5">
            <div>
              <p className="text-sm font-medium text-fg">
                Does this describe your business?
              </p>
              <p className="text-sm text-fg-muted">
                Confirming moves you on to your ideal customer profile. You can keep
                editing afterwards.
              </p>
            </div>
            <Button onClick={() => confirm.mutate()} loading={confirm.isPending}>
              Confirm and continue
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
