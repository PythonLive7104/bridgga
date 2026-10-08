"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Reveals its children once they scroll into view.
 *
 * Two things this does that a plain CSS animation cannot:
 *
 * 1. It checks `prefers-reduced-motion` in JS and renders the content already
 *    visible, rather than animating it to 0.01ms. The CSS override in
 *    globals.css would collapse the duration but still run the keyframes,
 *    which can flash.
 * 2. It renders visible when IntersectionObserver is unavailable, so a failure
 *    mode is "no animation", never "invisible content". Content that depends
 *    on JS to become visible is content a crawler may never see.
 */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }

    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            // One-shot: re-animating on every scroll past is a distraction.
            observer.disconnect();
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.1 },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={visible && delay ? { transitionDelay: `${delay}ms` } : undefined}
      className={cn(
        "transition-all duration-700 ease-out motion-reduce:transition-none",
        visible ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0",
        className,
      )}
    >
      {children}
    </div>
  );
}
