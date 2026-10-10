"use client";

import { AlertTriangle, Check, Loader2 } from "lucide-react";

import type { OnboardingStep } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * The step rail (PRD section 25).
 *
 * Five steps, named, with the current one marked — so somebody three screens
 * in knows how much is left and somebody returning knows where they stopped.
 * The states come from the server, which derives them from the records, so
 * this cannot show a tick for something that is not actually set up.
 *
 * `running` and `failed` get their own marks rather than being folded into
 * "not done". Step two is a crawl and a model call; the minute it takes is
 * the minute the customer is deciding whether this works, and an unfinished
 * circle would be the wrong thing to show them.
 */

function Mark({ state }: { state: string }) {
  if (state === "done") {
    return (
      <span className="flex size-5 items-center justify-center rounded-full bg-accent text-accent-fg">
        <Check aria-hidden className="size-3" />
      </span>
    );
  }
  if (state === "running") {
    return (
      <span className="flex size-5 items-center justify-center rounded-full border border-accent text-accent">
        <Loader2 aria-hidden className="size-3 animate-spin" />
      </span>
    );
  }
  if (state === "failed") {
    return (
      <span className="flex size-5 items-center justify-center rounded-full border border-signal-warm text-signal-warm">
        <AlertTriangle aria-hidden className="size-3" />
      </span>
    );
  }
  return (
    <span
      className={cn(
        "flex size-5 items-center justify-center rounded-full border",
        state === "current" ? "border-accent" : "border-border",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          state === "current" ? "bg-accent" : "bg-border-strong",
        )}
      />
    </span>
  );
}

export function OnboardingProgress({
  steps,
  current,
}: {
  steps: OnboardingStep[];
  current: string;
}) {
  const done = steps.filter((step) => step.state === "done").length;

  return (
    <nav aria-label="Setup progress" className="space-y-3">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-accent">
        Step {Math.min(done + 1, steps.length)} of {steps.length}
      </p>
      <ol className="space-y-2">
        {steps.map((step) => (
          <li key={step.key} className="flex items-start gap-2.5">
            <Mark state={step.state} />
            <div className="min-w-0">
              <p
                className={cn(
                  "text-sm",
                  step.key === current ? "font-medium text-fg" : "text-fg-muted",
                )}
                aria-current={step.key === current ? "step" : undefined}
              >
                {step.label}
              </p>
              {step.detail ? (
                <p className="truncate text-xs text-fg-subtle">{step.detail}</p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </nav>
  );
}
