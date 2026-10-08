"use client";

import { Check, Pencil, Undo2 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { FieldMeta } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * One editable field from the company profile.
 *
 * PRD section 26 requires every AI-generated value to be editable, which on
 * its own would be an ordinary form. What makes this component rather than a
 * form is the second requirement that follows from re-analysis: the customer
 * has to be able to tell their own correction apart from the agent's guess,
 * and get back to the agent's version when the correction was the mistake.
 *
 * So each field shows its provenance -- "Edited" with a revert control, or
 * nothing at all when it is still the agent's text -- and the empty state
 * says *why* a field is empty, because for a field like pricing, blank is a
 * finding ("the site publishes no prices") rather than a gap.
 */

interface BaseProps {
  label: string;
  meta?: FieldMeta;
  /** Shown when the value is empty: say why, do not just show nothing. */
  emptyHint?: string;
  readOnly?: boolean;
  onSave: (value: string | string[]) => void;
  onRevert?: () => void;
  isSaving?: boolean;
}

interface TextFieldProps extends BaseProps {
  value: string;
  multiline?: boolean;
}

interface ListFieldProps extends BaseProps {
  value: string[];
}

function FieldFrame({
  label,
  meta,
  readOnly,
  isEditing,
  onEdit,
  onRevert,
  children,
}: {
  label: string;
  meta?: FieldMeta;
  readOnly?: boolean;
  isEditing: boolean;
  onEdit: () => void;
  onRevert?: () => void;
  children: React.ReactNode;
}) {
  const edited = meta?.edited ?? false;

  return (
    <div className="flex flex-col gap-1.5 border-b border-border/60 py-4 last:border-0">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium text-fg">{label}</h3>
        {edited ? (
          <span className="rounded-full bg-bg-subtle px-2 py-0.5 text-[11px] font-medium text-fg-muted">
            Edited
          </span>
        ) : null}
        <div className="ml-auto flex items-center gap-1">
          {edited && onRevert && !readOnly ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={onRevert}
              // Spelled out because "Revert" alone does not say what it
              // reverts to, and the agent's value may be one the customer
              // deliberately replaced.
              title="Discard this edit and restore what the AI produced"
            >
              <Undo2 aria-hidden className="size-3.5" />
              Revert to AI
            </Button>
          ) : null}
          {!isEditing && !readOnly ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={onEdit}
              aria-label={`Edit ${label}`}
            >
              <Pencil aria-hidden className="size-3.5" />
              Edit
            </Button>
          ) : null}
        </div>
      </div>
      {children}
    </div>
  );
}

function EmptyValue({ hint }: { hint?: string }) {
  return (
    <p className="text-sm italic text-fg-subtle">{hint ?? "The website did not say."}</p>
  );
}

export function EditableText({
  label,
  value,
  meta,
  emptyHint,
  multiline = false,
  readOnly = false,
  onSave,
  onRevert,
  isSaving,
}: TextFieldProps) {
  const [isEditing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(value);

  // The agent can finish while a field sits open; take the new value only when
  // the field is closed, so a re-analysis never overwrites what is being typed.
  React.useEffect(() => {
    if (!isEditing) setDraft(value);
  }, [value, isEditing]);

  const commit = () => {
    setEditing(false);
    if (draft !== value) onSave(draft);
  };

  const cancel = () => {
    setDraft(value);
    setEditing(false);
  };

  return (
    <FieldFrame
      label={label}
      meta={meta}
      readOnly={readOnly}
      isEditing={isEditing}
      onEdit={() => setEditing(true)}
      onRevert={onRevert}
    >
      {isEditing ? (
        <div className="flex flex-col gap-2">
          {multiline ? (
            <textarea
              autoFocus
              rows={3}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") cancel();
              }}
              aria-label={label}
              className="w-full rounded-[var(--radius-control)] border border-border bg-surface p-3 text-sm text-fg focus:outline-none focus:ring-2 focus:ring-accent"
            />
          ) : (
            <Input
              autoFocus
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") commit();
                if (event.key === "Escape") cancel();
              }}
              aria-label={label}
            />
          )}
          <div className="flex gap-2">
            <Button size="sm" onClick={commit} disabled={isSaving}>
              <Check aria-hidden className="size-3.5" />
              Save
            </Button>
            <Button size="sm" variant="ghost" onClick={cancel}>
              Cancel
            </Button>
          </div>
        </div>
      ) : value ? (
        <p className="whitespace-pre-wrap text-sm text-fg-muted">{value}</p>
      ) : (
        <EmptyValue hint={emptyHint} />
      )}
    </FieldFrame>
  );
}

export function EditableList({
  label,
  value,
  meta,
  emptyHint,
  readOnly = false,
  onSave,
  onRevert,
  isSaving,
}: ListFieldProps) {
  const [isEditing, setEditing] = React.useState(false);
  // Edited as lines of text rather than as a tag widget: people paste lists,
  // and a line-per-item box accepts a paste that a chip input mangles.
  const [draft, setDraft] = React.useState(value.join("\n"));

  React.useEffect(() => {
    if (!isEditing) setDraft(value.join("\n"));
  }, [value, isEditing]);

  const commit = () => {
    setEditing(false);
    const next = draft
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (next.join("\u0000") !== value.join("\u0000")) onSave(next);
  };

  const cancel = () => {
    setDraft(value.join("\n"));
    setEditing(false);
  };

  return (
    <FieldFrame
      label={label}
      meta={meta}
      readOnly={readOnly}
      isEditing={isEditing}
      onEdit={() => setEditing(true)}
      onRevert={onRevert}
    >
      {isEditing ? (
        <div className="flex flex-col gap-2">
          <textarea
            autoFocus
            rows={Math.max(3, value.length + 1)}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") cancel();
            }}
            aria-label={`${label}, one per line`}
            className="w-full rounded-[var(--radius-control)] border border-border bg-surface p-3 text-sm text-fg focus:outline-none focus:ring-2 focus:ring-accent"
          />
          <p className="text-xs text-fg-subtle">One per line.</p>
          <div className="flex gap-2">
            <Button size="sm" onClick={commit} disabled={isSaving}>
              <Check aria-hidden className="size-3.5" />
              Save
            </Button>
            <Button size="sm" variant="ghost" onClick={cancel}>
              Cancel
            </Button>
          </div>
        </div>
      ) : value.length ? (
        <ul className="flex flex-wrap gap-1.5">
          {value.map((item) => (
            <li
              key={item}
              className="rounded-md border border-border bg-bg-subtle px-2 py-1 text-xs text-fg-muted"
            >
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <EmptyValue hint={emptyHint} />
      )}
    </FieldFrame>
  );
}

/** A claim with the source it came from (PRD sections 58 and 119). */
export function EvidenceRow({
  claim,
  quote,
  sourceUrl,
  confidence,
}: {
  claim: string;
  quote: string;
  sourceUrl: string;
  confidence: string;
}) {
  return (
    <li className="border-l-2 border-border py-2 pl-3">
      <p className="text-sm text-fg">{claim}</p>
      {quote ? (
        <p className="mt-1 text-sm italic text-fg-muted">&ldquo;{quote}&rdquo;</p>
      ) : null}
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-fg-subtle">
        {sourceUrl ? (
          <a
            href={sourceUrl}
            // Untrusted outbound link: noreferrer also stops the target
            // learning which customer's profile linked to it.
            rel="noopener noreferrer nofollow"
            target="_blank"
            className="underline underline-offset-2 hover:text-fg"
          >
            {sourceUrl}
          </a>
        ) : null}
        {confidence ? (
          <span
            className={cn(
              "rounded-full px-2 py-0.5",
              confidence === "low"
                ? "bg-signal-warm/15 text-signal-warm"
                : "bg-bg-subtle",
            )}
          >
            {confidence} confidence
          </span>
        ) : null}
      </div>
    </li>
  );
}
