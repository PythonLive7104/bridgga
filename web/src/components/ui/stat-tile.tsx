import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * A single headline metric.
 *
 * The label sits above the value so the number is the thing the eye lands on,
 * and values use tabular figures so a row of tiles does not jitter as data
 * updates.
 */
export function StatTile({
  label,
  value,
  hint,
  className,
}: {
  label: string;
  value: string;
  hint?: string;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardContent className="p-5">
        <p className="text-xs font-medium uppercase tracking-wider text-fg-subtle">
          {label}
        </p>
        <p className={cn("tabular mt-2 text-3xl font-semibold text-fg")}>{value}</p>
        {hint ? <p className="mt-1 text-xs text-fg-muted">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
