"use client";

import { Plus, Radar, Trash2, Undo2 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  SIGNAL_TYPES,
  type FieldMeta,
  type PainSignal,
  type SignalType,
} from "@/lib/api/types";

/**
 * The pain-signal editor (PRD section 27, third block).
 *
 * The type is a select, never a text box, and that is the point of this
 * component existing instead of another list field. The vocabulary is closed
 * (PRD section 33) because it is the join between what a customer says they
 * are watching for and what the signal engine can actually detect. A free-text
 * signal would be accepted here, look perfectly reasonable on screen, and then
 * match nothing at all -- a failure that shows up weeks later as "why does
 * this ICP never surface anyone?".
 *
 * The description is required for the same reason in miniature: "hiring" says
 * to watch for hiring, but not *what* hiring, and every growing company hires.
 */

const TYPE_LABELS: Record<SignalType, string> = {
  funding: "Raised funding",
  hiring: "Hiring",
  expansion: "Expanding",
  acquisition: "Acquisition",
  new_office: "Opened an office",
  leadership_change: "Leadership change",
  new_pages: "New website pages",
  product_launch: "Launched a product",
  pricing_change: "Changed pricing",
  technology_change: "Changed technology",
  website_change: "Website changed",
  advertising: "Started advertising",
  content_growth: "Publishing more",
  social_activity: "Social activity",
  procurement: "Procurement activity",
  other: "Something else",
};

const EMPTY: PainSignal = { type: "hiring", description: "", why_it_matters: "" };

export function PainSignalEditor({
  value,
  meta,
  readOnly,
  isSaving,
  onSave,
  onRevert,
}: {
  value: PainSignal[];
  meta?: FieldMeta;
  readOnly?: boolean;
  isSaving?: boolean;
  onSave: (next: PainSignal[]) => void;
  onRevert?: () => void;
}) {
  const [draft, setDraft] = React.useState<PainSignal[]>(value);
  const [isEditing, setEditing] = React.useState(false);

  React.useEffect(() => {
    if (!isEditing) setDraft(value);
  }, [value, isEditing]);

  const update = (index: number, patch: Partial<PainSignal>) =>
    setDraft((current) =>
      current.map((signal, i) => (i === index ? { ...signal, ...patch } : signal)),
    );

  const commit = () => {
    setEditing(false);
    // A signal with no description is refused by the API, so it is dropped
    // here rather than sent to fail validation.
    onSave(draft.filter((signal) => signal.description.trim()));
  };

  if (!isEditing) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          {meta?.edited ? (
            <span className="rounded-full bg-bg-subtle px-2 py-0.5 text-[11px] font-medium text-fg-muted">
              Edited
            </span>
          ) : null}
          <div className="ml-auto flex gap-1">
            {meta?.edited && onRevert && !readOnly ? (
              <Button variant="ghost" size="sm" onClick={onRevert}>
                <Undo2 aria-hidden className="size-3.5" />
                Revert to AI
              </Button>
            ) : null}
            {!readOnly ? (
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
                Edit signals
              </Button>
            ) : null}
          </div>
        </div>

        {value.length ? (
          <ul className="space-y-2">
            {value.map((signal, index) => (
              <li
                key={`${signal.type}-${index}`}
                className="rounded-[var(--radius-control)] border border-border p-3"
              >
                <div className="flex items-center gap-2">
                  <Radar aria-hidden className="size-3.5 text-accent" />
                  <span className="text-xs font-medium uppercase tracking-wide text-fg-muted">
                    {TYPE_LABELS[signal.type] ?? signal.type}
                  </span>
                </div>
                <p className="mt-1 text-sm text-fg">{signal.description}</p>
                {signal.why_it_matters ? (
                  <p className="mt-1 text-sm text-fg-subtle">{signal.why_it_matters}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm italic text-fg-subtle">
            No signals yet. These are what we watch for to tell you a company is worth
            contacting now rather than someday.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {draft.map((signal, index) => (
        <div
          key={index}
          className="space-y-2 rounded-[var(--radius-control)] border border-border p-3"
        >
          <div className="flex items-end gap-2">
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor={`signal-type-${index}`}
                className="text-sm font-medium text-fg"
              >
                Signal
              </label>
              <select
                id={`signal-type-${index}`}
                value={signal.type}
                onChange={(event) =>
                  update(index, { type: event.target.value as SignalType })
                }
                className="h-10 rounded-[var(--radius-control)] border border-border bg-surface px-3 text-sm text-fg"
              >
                {SIGNAL_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {TYPE_LABELS[type]}
                  </option>
                ))}
              </select>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="mb-0.5 ml-auto"
              onClick={() => setDraft((current) => current.filter((_, i) => i !== index))}
              aria-label={`Remove signal ${index + 1}`}
            >
              <Trash2 aria-hidden className="size-3.5" />
              Remove
            </Button>
          </div>

          <Input
            label="What to look for"
            value={signal.description}
            onChange={(event) => update(index, { description: event.target.value })}
            placeholder="Hiring fleet or logistics managers"
          />
          <Input
            label="Why it matters"
            hint="Optional. Why this event means they may need what you sell."
            value={signal.why_it_matters ?? ""}
            onChange={(event) => update(index, { why_it_matters: event.target.value })}
          />
        </div>
      ))}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setDraft((current) => [...current, { ...EMPTY }])}
        >
          <Plus aria-hidden className="size-3.5" />
          Add a signal
        </Button>
        <Button size="sm" onClick={commit} disabled={isSaving}>
          Save signals
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setDraft(value);
            setEditing(false);
          }}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
