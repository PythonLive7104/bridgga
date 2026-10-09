"use client";

import { RotateCcw, SlidersHorizontal } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { useScoringProfile } from "@/lib/hooks/use-prospects";

/**
 * The section 32 weighting, editable (PRD section 32: "Weights must be
 * configurable").
 *
 * It sits beside the prospect list rather than in a settings area, because
 * the weighting is only meaningful in terms of the list it reorders: change a
 * number here and the ranking next to it changes, which is the only way to
 * tell whether the change was right.
 *
 * The numbers are not required to add up to 100. A business that types 10
 * into every box means "weigh these equally", and the server normalises by
 * whatever they total — so the editor shows each weight's share rather than
 * nagging about a sum.
 */

export function WeightsEditor({ canManage }: { canManage: boolean }) {
  const { profile, update, reset } = useScoringProfile();
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState<Record<string, number> | null>(null);

  const weights = draft ?? profile?.weights ?? {};
  const total = Object.values(weights).reduce((sum, value) => sum + value, 0);
  const dirty =
    draft !== null &&
    profile !== undefined &&
    JSON.stringify(draft) !== JSON.stringify(profile.weights);

  if (!profile) return null;

  return (
    <div className="border-t border-border pt-4">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-fg-subtle hover:text-fg"
      >
        <SlidersHorizontal aria-hidden className="size-3" />
        Score weighting
        {profile.is_customised ? (
          <span className="ml-auto text-[10px] normal-case text-accent">customised</span>
        ) : null}
      </button>

      {open ? (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-fg-subtle">
            What each factor is worth. Totals need not come to 100 — each one counts for
            its share of {total}.
          </p>

          <ul className="space-y-2.5">
            {profile.components.map((component) => {
              const value = weights[component.component] ?? component.weight;
              return (
                <li key={component.component}>
                  <label
                    htmlFor={`weight-${component.component}`}
                    className="flex items-baseline justify-between gap-2 text-xs text-fg-muted"
                  >
                    <span>{component.label}</span>
                    <span className="tabular text-fg-subtle">
                      {total ? Math.round((value / total) * 100) : 0}%
                    </span>
                  </label>
                  <input
                    id={`weight-${component.component}`}
                    type="range"
                    min={0}
                    max={50}
                    step={1}
                    value={value}
                    disabled={!canManage}
                    onChange={(event) =>
                      setDraft({
                        ...weights,
                        [component.component]: Number(event.target.value),
                      })
                    }
                    className="mt-1 w-full accent-[var(--accent)] disabled:opacity-50"
                  />
                </li>
              );
            })}
          </ul>

          {canManage ? (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={!dirty}
                loading={update.isPending}
                onClick={() => {
                  if (draft) update.mutate(draft, { onSuccess: () => setDraft(null) });
                }}
              >
                Save and rescore
              </Button>
              <Button
                size="sm"
                variant="ghost"
                loading={reset.isPending}
                onClick={() => {
                  setDraft(null);
                  reset.mutate();
                }}
              >
                <RotateCcw aria-hidden className="size-3.5" />
                Defaults
              </Button>
            </div>
          ) : (
            <p className="text-xs text-fg-subtle">
              Only someone who can manage prospects may change these.
            </p>
          )}

          {/* Said plainly, because the effect is larger than the control
              suggests: saving recomputes every stored score. */}
          {dirty ? (
            <p className="text-xs text-fg-subtle">
              Saving rescores every prospect in this workspace.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
