import * as React from "react";

import { cn, scoreBand, type SignalBand } from "@/lib/utils";

type Tone = "neutral" | "accent" | "positive" | "negative" | SignalBand;

const TONES: Record<Tone, string> = {
  neutral: "bg-bg-subtle text-fg-muted border-border",
  accent: "bg-accent-subtle text-accent border-transparent",
  positive: "bg-positive/12 text-positive border-transparent",
  negative: "bg-negative/12 text-negative border-transparent",
  hot: "bg-signal-hot/14 text-signal-hot border-transparent",
  warm: "bg-signal-warm/14 text-signal-warm border-transparent",
  cold: "bg-signal-cold/14 text-signal-cold border-transparent",
};

export function Badge({
  className,
  tone = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5",
        "text-xs font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
      {...props}
    />
  );
}

/**
 * An opportunity score, rendered with its band.
 *
 * Colour alone never carries the meaning: the number is always present, so the
 * badge still reads correctly for colour-blind users and in monochrome
 * (PRD section 112).
 */
export function ScoreBadge({ score, className }: { score: number; className?: string }) {
  const band = scoreBand(score);
  return (
    <Badge tone={band} className={cn("tabular", className)}>
      <span className="sr-only">Opportunity score </span>
      {score}
      <span className="opacity-70">/100</span>
    </Badge>
  );
}
