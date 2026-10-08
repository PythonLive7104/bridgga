import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge conditional class names, with later Tailwind utilities winning. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Compact number formatting for stat tiles: 12400 -> "12.4K". */
export function formatCompact(value: number, locale = "en"): string {
  return new Intl.NumberFormat(locale, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/**
 * Money is handled as integer minor units everywhere, matching the backend.
 * Passing a float through here would reintroduce the rounding error the
 * backend's integer columns exist to avoid.
 */
export function formatMoneyMinor(
  minorUnits: number,
  currency: string,
  locale = "en",
): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(minorUnits / 100);
}

export type SignalBand = "hot" | "warm" | "cold";

/**
 * Opportunity score to a semantic band (PRD section 32 scores 0-100).
 * Centralised so a score reads the same in a table, a badge and a chart.
 */
export function scoreBand(score: number): SignalBand {
  if (score >= 75) return "hot";
  if (score >= 45) return "warm";
  return "cold";
}
