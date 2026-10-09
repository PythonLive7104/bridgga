"use client";

import { Bookmark, Mail, MailX, Radar, Search, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import type { Prospect } from "@/lib/api/types";
import {
  useProspectFacets,
  useProspects,
  useSavedSearches,
  type ProspectQuery,
} from "@/lib/hooks/use-prospects";
import { useSession } from "@/lib/hooks/use-session";
import { cn } from "@/lib/utils";

/**
 * The prospect table (PRD section 117), over the section 29 filter set.
 *
 * Two decisions shape it.
 *
 * **The signal column shows the signal, not a count.** "3 signals" tells a rep
 * nothing they can act on; "Hiring fleet supervisors, 2 days ago" is the
 * reason to open the row. The evidence is the product (section 58), and
 * hiding it behind a number throws that away to save a few pixels.
 *
 * **Contactability is shown, not implied.** A row whose only address bounced
 * looks identical to a good one until somebody tries to send, so the state is
 * on the row where it changes what a person does next.
 */

const DEBOUNCE_MS = 250;

function timeAgo(value: string | null): string {
  if (!value) return "";
  const days = Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "last month" : `${months} months ago`;
}

function SignalCell({ prospect }: { prospect: Prospect }) {
  const [first, ...rest] = prospect.signals;
  if (!first) return <span className="text-sm text-fg-subtle">&mdash;</span>;

  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5">
        <Radar aria-hidden className="size-3.5 shrink-0 text-accent" />
        <span className="truncate text-sm text-fg">{first.title}</span>
      </div>
      <p className="mt-0.5 text-xs text-fg-subtle">
        {first.event_type.replace(/_/g, " ")}
        {first.occurred_at ? ` · ${timeAgo(first.occurred_at)}` : null}
        {rest.length ? ` · +${rest.length} more` : null}
      </p>
    </div>
  );
}

function ContactCell({ prospect }: { prospect: Prospect }) {
  const contact = prospect.contact;
  if (!contact) {
    return <span className="text-sm text-fg-subtle">No contact yet</span>;
  }

  return (
    <div className="min-w-0">
      <p className="truncate text-sm text-fg">{contact.name}</p>
      <p className="flex items-center gap-1 text-xs text-fg-subtle">
        {contact.contactable ? (
          <Mail aria-hidden className="size-3" />
        ) : (
          <MailX aria-hidden className="size-3 text-negative" />
        )}
        <span className="truncate">{contact.job_title || contact.email_status}</span>
      </p>
    </div>
  );
}

function FilterChips({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: { value: string; count: number }[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  if (!options.length) return null;

  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const active = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onToggle(option.value)}
              aria-pressed={active}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs transition-colors",
                active
                  ? "border-accent bg-accent text-accent-fg"
                  : "border-border text-fg-muted hover:border-border-strong",
              )}
            >
              {option.value}
              <span className={cn("ml-1", active ? "opacity-80" : "text-fg-subtle")}>
                {option.count}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function ProspectsPage() {
  const { can } = useSession();
  const [text, setText] = React.useState("");
  const [query, setQuery] = React.useState<ProspectQuery>({});
  const facets = useProspectFacets();
  const { prospects, isLoading, isFetching, data } = useProspects(query);
  const { searches, save } = useSavedSearches();

  const canManage = can("prospect.manage");

  // Debounced, so a search is one request per pause rather than one per
  // keystroke -- the difference between a responsive table and a hot database.
  React.useEffect(() => {
    const timer = setTimeout(
      () => setQuery((current) => ({ ...current, q: text || undefined })),
      DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [text]);

  const toggle = (key: "country" | "industry" | "employee_range") => (value: string) =>
    setQuery((current) => {
      const existing = current[key] ?? [];
      const next = existing.includes(value)
        ? existing.filter((item) => item !== value)
        : [...existing, value];
      return { ...current, [key]: next.length ? next : undefined };
    });

  const activeFilters =
    (query.country?.length ?? 0) +
    (query.industry?.length ?? 0) +
    (query.employee_range?.length ?? 0) +
    (query.contactable ? 1 : 0);

  const total = data?.results.length ?? 0;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-fg">Prospects</h1>
          <p className="mt-1 text-sm text-fg-muted">
            Companies worth a conversation, with the evidence that says why.
          </p>
        </div>
        {canManage && (query.q || activeFilters) ? (
          <Button
            variant="secondary"
            onClick={() => {
              const name = window.prompt("Name this search");
              if (name) save.mutate({ name, filters: query, is_shared: true });
            }}
            loading={save.isPending}
          >
            <Bookmark aria-hidden className="size-4" />
            Save this search
          </Button>
        ) : null}
      </header>

      <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="space-y-5">
          <Input
            label="Search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Name, industry, city"
            aria-label="Search prospects"
          />

          <label className="flex items-center gap-2 text-sm text-fg-muted">
            <input
              type="checkbox"
              checked={Boolean(query.contactable)}
              onChange={(event) =>
                setQuery((current) => ({
                  ...current,
                  contactable: event.target.checked || undefined,
                }))
              }
              className="size-4 rounded border-border accent-[var(--accent)]"
            />
            Reachable today
          </label>

          <FilterChips
            label="Country"
            options={facets.data?.countries ?? []}
            selected={query.country ?? []}
            onToggle={toggle("country")}
          />
          <FilterChips
            label="Industry"
            options={facets.data?.industries ?? []}
            selected={query.industry ?? []}
            onToggle={toggle("industry")}
          />
          <FilterChips
            label="Size"
            options={facets.data?.employee_ranges ?? []}
            selected={query.employee_range ?? []}
            onToggle={toggle("employee_range")}
          />

          {activeFilters || query.q ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setText("");
                setQuery({});
              }}
            >
              <X aria-hidden className="size-3.5" />
              Clear filters
            </Button>
          ) : null}

          {searches.length ? (
            <div className="space-y-1.5 border-t border-border pt-4">
              <p className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
                Saved searches
              </p>
              <ul className="space-y-1">
                {searches.map((saved) => (
                  <li key={saved.id}>
                    <button
                      type="button"
                      onClick={() => setQuery(saved.filters as ProspectQuery)}
                      className="text-sm text-fg-muted underline-offset-2 hover:text-fg hover:underline"
                    >
                      {saved.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </aside>

        <div className="min-w-0 space-y-3">
          <p className="text-sm text-fg-subtle" aria-live="polite">
            {isLoading ? "Searching…" : `${total} prospect${total === 1 ? "" : "s"}`}
            {isFetching && !isLoading ? " · updating" : null}
          </p>

          {!isLoading && total === 0 ? (
            <EmptyState
              title="No prospects match"
              description="Nothing here yet. Import a list, or widen the filters — a search that returns nothing usually has one filter too many."
              action={
                <Button variant="secondary" onClick={() => setQuery({})}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[56rem] text-left">
                    <caption className="sr-only">
                      Prospects matching the current filters
                    </caption>
                    <thead>
                      <tr className="border-b border-border text-xs uppercase tracking-wide text-fg-subtle">
                        <th scope="col" className="px-4 py-3 font-medium">
                          Company
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Contact
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Location
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Signal
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Status
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {prospects.map((prospect) => (
                        <tr
                          key={prospect.id}
                          className="border-b border-border/60 last:border-0 hover:bg-bg-subtle/60"
                        >
                          <td className="max-w-xs px-4 py-3">
                            <p className="truncate font-medium text-fg">
                              {prospect.name}
                            </p>
                            <p className="truncate text-xs text-fg-subtle">
                              {prospect.industry || prospect.domain}
                            </p>
                          </td>
                          <td className="max-w-xs px-4 py-3">
                            <ContactCell prospect={prospect} />
                          </td>
                          <td className="px-4 py-3 text-sm text-fg-muted">
                            {[prospect.city, prospect.country]
                              .filter(Boolean)
                              .join(", ") || "—"}
                          </td>
                          <td className="max-w-sm px-4 py-3">
                            <SignalCell prospect={prospect} />
                          </td>
                          <td className="px-4 py-3">
                            <span className="text-sm text-fg-muted">
                              {prospect.lead?.status ?? "Not a lead yet"}
                            </span>
                            {prospect.is_stale ? (
                              <p
                                className="text-xs text-signal-warm"
                                title="Nothing has re-confirmed this record recently"
                              >
                                Stale
                              </p>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {data?.search_backend === "substring" ? (
            <p className="flex items-center gap-1.5 text-xs text-fg-subtle">
              <Search aria-hidden className="size-3" />
              {/* Stated rather than hidden: ranked results need Postgres, and a
                  developer comparing local and deployed results should know. */}
              Ranked search needs Postgres; this result used substring matching.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
