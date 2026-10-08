import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Marketing layout primitives.
 *
 * Every section goes through these so vertical rhythm, max width and the
 * eyebrow/heading/sub pattern stay identical down the page. Hand-rolling each
 * section is how a landing page ends up with six slightly different spacings.
 */

export function Section({
  className,
  tone = "default",
  children,
  ...props
}: React.HTMLAttributes<HTMLElement> & { tone?: "default" | "subtle" | "wash" }) {
  return (
    <section
      className={cn(
        "border-t border-border",
        tone === "subtle" && "bg-bg-subtle",
        tone === "wash" && "gradient-wash",
        className,
      )}
      {...props}
    >
      <div className="mx-auto max-w-6xl px-4 py-20 sm:py-28">{children}</div>
    </section>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  align = "center",
  className,
}: {
  eyebrow?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  align?: "center" | "left";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-4",
        align === "center" ? "mx-auto max-w-2xl text-center" : "max-w-xl",
        className,
      )}
    >
      {eyebrow ? (
        <div className={align === "center" ? "mx-auto" : ""}>
          <Badge tone="accent">{eyebrow}</Badge>
        </div>
      ) : null}
      <h2 className="text-headline text-fg">{title}</h2>
      {description ? <p className="text-fg-muted">{description}</p> : null}
    </div>
  );
}

/** A labelled band of numbers. Used for definitions, never for invented results. */
export function StatBand({
  items,
  className,
}: {
  items: { value: string; label: string }[];
  className?: string;
}) {
  return (
    <dl
      className={cn(
        "grid gap-px overflow-hidden rounded-[var(--radius-card)] border border-border bg-border sm:grid-cols-2 lg:grid-cols-4",
        className,
      )}
    >
      {items.map((item) => (
        <div key={item.label} className="bg-surface px-5 py-6 text-center">
          <dt className="sr-only">{item.label}</dt>
          <dd>
            <span className="tabular block text-2xl font-semibold text-fg">
              {item.value}
            </span>
            <span className="mt-1 block text-sm text-fg-muted">{item.label}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
