"use client";

import { AlertTriangle, CheckCircle2, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EditableList, EditableText } from "@/components/intelligence/editable-field";
import { PainSignalEditor } from "@/components/intelligence/pain-signals";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import type { ICP, ICPField, PainSignal } from "@/lib/api/types";
import { useICPs } from "@/lib/hooks/use-icp";
import { useSession } from "@/lib/hooks/use-session";

/**
 * The ICP builder (PRD section 27).
 *
 * Laid out in the three blocks the PRD names -- company profile, buyer
 * profile, pain signals -- because those are three different questions and
 * running them together as one long form makes none of them answerable.
 *
 * Several ICPs are supported, with one active, since a real business sells to
 * more than one kind of buyer. The active one is what prospect discovery and
 * campaigns read, so which one it is has to be obvious rather than inferred.
 */

const COMPANY_FIELDS: { field: ICPField; label: string; list?: boolean }[] = [
  { field: "industries", label: "Industries", list: true },
  { field: "countries", label: "Countries", list: true },
  { field: "employee_range", label: "Employee range" },
  { field: "business_size", label: "Estimated size" },
  { field: "business_models", label: "Business models", list: true },
  { field: "technologies", label: "Technology", list: true },
  { field: "growth_stage", label: "Growth stage" },
];

const BUYER_FIELDS: { field: ICPField; label: string }[] = [
  { field: "job_titles", label: "Job titles" },
  { field: "departments", label: "Departments" },
  { field: "seniority", label: "Seniority" },
  { field: "responsibilities", label: "Responsibilities" },
];

export default function ICPPage() {
  const { can } = useSession();
  const { icps, isLoading, generate, regenerate, save, reset, activate } = useICPs();
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const canManage = can("icp.manage");
  const selected: ICP | undefined =
    icps.find((icp) => icp.id === selectedId) ??
    icps.find((icp) => icp.is_active) ??
    icps[0];

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy>
        <div className="h-8 w-56 animate-pulse rounded bg-bg-subtle" />
        <div className="h-64 animate-pulse rounded-[var(--radius-card)] bg-bg-subtle" />
      </div>
    );
  }

  if (!icps.length) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">
          Ideal customer profile
        </h1>
        <EmptyState
          title="No ICP yet"
          description="We build this from your company profile: the kind of organisation most likely to need what you sell, who inside it decides, and what to watch for. Confirm your company first, then generate."
          action={
            canManage ? (
              <div className="flex flex-wrap justify-center gap-2">
                <Button onClick={() => generate.mutate()} loading={generate.isPending}>
                  <Sparkles aria-hidden className="size-4" />
                  Generate from my company
                </Button>
                <Link href="/company-profile">
                  <Button variant="secondary">Review my company first</Button>
                </Link>
              </div>
            ) : null
          }
        />
        {generate.isError ? (
          <p role="alert" className="text-sm text-negative">
            {(generate.error as Error).message}
          </p>
        ) : null}
      </div>
    );
  }

  if (!selected) return null;

  const field = (name: ICPField) => ({
    meta: selected.fields_meta[name],
    readOnly: !canManage,
    isSaving: save.isPending,
    onSave: (value: string | string[]) =>
      save.mutate({ id: selected.id, changes: { [name]: value } }),
    onRevert: () => reset.mutate({ id: selected.id, fields: [name] }),
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-fg">
            Ideal customer profile
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-fg-muted">
            Who to sell to, who decides, and what to watch for. Everything is editable,
            and your edits survive the next generation.
          </p>
        </div>
        {canManage ? (
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => regenerate.mutate(selected.id)}
              loading={regenerate.isPending}
            >
              <RefreshCw aria-hidden className="size-4" />
              Re-generate
            </Button>
            <Button onClick={() => generate.mutate()} loading={generate.isPending}>
              <Sparkles aria-hidden className="size-4" />
              New ICP
            </Button>
          </div>
        ) : null}
      </header>

      {icps.length > 1 ? (
        <nav aria-label="Ideal customer profiles" className="flex flex-wrap gap-2">
          {icps.map((icp) => (
            <button
              key={icp.id}
              type="button"
              onClick={() => setSelectedId(icp.id)}
              aria-current={icp.id === selected.id ? "true" : undefined}
              className={
                icp.id === selected.id
                  ? "rounded-full bg-accent px-3 py-1.5 text-sm text-accent-fg"
                  : "rounded-full border border-border px-3 py-1.5 text-sm text-fg-muted hover:border-border-strong"
              }
            >
              {icp.name || "Untitled"}
              {icp.is_active ? " · active" : ""}
            </button>
          ))}
        </nav>
      ) : null}

      {selected.status === "failed" && selected.generation_error ? (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-[var(--radius-control)] bg-negative/10 p-3 text-sm text-negative"
        >
          <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
          {selected.generation_error}
        </p>
      ) : null}

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
          <div className="min-w-64 flex-1">
            <EditableText label="Name" value={selected.name} {...field("name")} />
          </div>
          {selected.is_active ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-positive/15 px-3 py-1 text-sm text-positive">
              <CheckCircle2 aria-hidden className="size-4" />
              Active
            </span>
          ) : canManage ? (
            <Button
              variant="secondary"
              onClick={() => activate.mutate(selected.id)}
              loading={activate.isPending}
            >
              Make this the active ICP
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>The company</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {COMPANY_FIELDS.map(({ field: name, label, list }) =>
              list ? (
                <EditableList
                  key={name}
                  label={label}
                  value={selected[name] as string[]}
                  {...field(name)}
                />
              ) : (
                <EditableText
                  key={name}
                  label={label}
                  value={selected[name] as string}
                  {...field(name)}
                />
              ),
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>The buyer</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {BUYER_FIELDS.map(({ field: name, label }) => (
              <EditableList
                key={name}
                label={label}
                value={selected[name] as string[]}
                {...field(name)}
              />
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>What to watch for</CardTitle>
        </CardHeader>
        <CardContent>
          <PainSignalEditor
            value={selected.pain_signals}
            meta={selected.fields_meta.pain_signals}
            readOnly={!canManage}
            isSaving={save.isPending}
            onSave={(next: PainSignal[]) =>
              save.mutate({ id: selected.id, changes: { pain_signals: next } })
            }
            onRevert={() => reset.mutate({ id: selected.id, fields: ["pain_signals"] })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Why this profile</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <EditableText
            label="Reasoning"
            value={selected.rationale}
            multiline
            emptyHint="No reasoning recorded yet."
            {...field("rationale")}
          />
        </CardContent>
      </Card>
    </div>
  );
}
