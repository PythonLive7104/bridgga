import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Empty state (PRD section 114).
 *
 * An empty module should say what the thing is and what to do next. A blank
 * panel reads as a broken page, and a fake chart reads as a lie.
 */
export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-[var(--radius-card)] border border-dashed border-border px-6 py-10 text-center",
        className,
      )}
    >
      <p className="text-sm font-medium text-fg">{title}</p>
      <p className="max-w-sm text-sm text-fg-muted">{description}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
