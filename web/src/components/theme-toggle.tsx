"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Theme control.
 *
 * Three states, not two: "system" has to be reachable, or a visitor whose OS
 * is set to dark can never get back to following it once they have tried light.
 *
 * The chosen value is written to `data-theme` on <html>, which globals.css
 * reads: `[data-theme="dark"]` forces dark, `:root:not([data-theme="light"])`
 * under the dark media query handles system, and absence means system.
 */

export const THEME_STORAGE_KEY = "bridgga-theme";

type Theme = "system" | "light" | "dark";

const ORDER: Theme[] = ["system", "light", "dark"];

const ICONS: Record<Theme, React.ComponentType<{ className?: string }>> = {
  system: Monitor,
  light: Sun,
  dark: Moon,
};

const LABELS: Record<Theme, string> = {
  system: "Theme: follow system",
  light: "Theme: light",
  dark: "Theme: dark",
};

function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", theme);
  }
}

function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Private browsing or blocked storage: fall through to system.
  }
  return "system";
}

export function ThemeToggle({ className }: { className?: string }) {
  // Starts as "system" on both server and client so the first render matches
  // and hydration does not warn; the stored value is adopted in the effect.
  const [theme, setTheme] = React.useState<Theme>("system");
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setTheme(readStoredTheme());
    setMounted(true);
  }, []);

  function cycle() {
    const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length] ?? "system";
    setTheme(next);
    applyTheme(next);
    try {
      if (next === "system") {
        localStorage.removeItem(THEME_STORAGE_KEY);
      } else {
        localStorage.setItem(THEME_STORAGE_KEY, next);
      }
    } catch {
      // Theme still applies for this page view even if it cannot be persisted.
    }
  }

  const Icon = ICONS[theme];

  return (
    <button
      type="button"
      onClick={cycle}
      // Until mounted the icon reflects the default rather than the stored
      // value, so keep it out of the accessibility tree for that first beat.
      aria-hidden={!mounted}
      tabIndex={mounted ? 0 : -1}
      aria-label={LABELS[theme]}
      title={LABELS[theme]}
      className={cn(
        "grid size-9 place-items-center rounded-[var(--radius-control)]",
        "text-fg-muted transition-colors hover:bg-bg-subtle hover:text-fg",
        className,
      )}
    >
      <Icon className="size-4" />
    </button>
  );
}

/**
 * Applies the stored theme before first paint.
 *
 * Without this the page renders in the system theme and then snaps to the
 * stored one — a visible flash on every navigation. It has to be inline and
 * synchronous in <head>, which is the one justified use of
 * dangerouslySetInnerHTML here: the content is a fixed literal with no
 * interpolation.
 */
export function ThemeScript() {
  const script = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t);}}catch(e){}})();`;
  return <script dangerouslySetInnerHTML={{ __html: script }} />;
}
