"use client";

import { Bell, Search } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { useSession } from "@/lib/hooks/use-session";

/**
 * Top bar: organization switcher, global search, notifications, identity.
 *
 * The switcher writes the chosen organization's public id into the
 * X-Organization header on subsequent requests; it never grants access on its
 * own, since the server re-verifies membership every time.
 */
export function AppTopbar() {
  const { me, organization, role, isLoading } = useSession();

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-bg px-4">
      <div className="flex min-w-0 items-center gap-2">
        {isLoading ? (
          <span className="h-5 w-32 animate-pulse rounded bg-bg-subtle" />
        ) : organization ? (
          <>
            <span className="truncate text-sm font-medium text-fg">
              {organization.name}
            </span>
            {role ? <Badge>{role.replace("_", " ")}</Badge> : null}
          </>
        ) : (
          <span className="text-sm text-fg-muted">No organization selected</span>
        )}
      </div>

      <div className="ml-auto flex items-center gap-1">
        <button
          type="button"
          aria-label="Search"
          className="grid size-9 place-items-center rounded-[var(--radius-control)] text-fg-muted transition-colors hover:bg-bg-subtle hover:text-fg"
        >
          <Search className="size-4" />
        </button>
        <button
          type="button"
          aria-label="Notifications"
          className="grid size-9 place-items-center rounded-[var(--radius-control)] text-fg-muted transition-colors hover:bg-bg-subtle hover:text-fg"
        >
          <Bell className="size-4" />
        </button>
        <ThemeToggle />
        <div
          aria-hidden
          className="ml-1 grid size-8 place-items-center rounded-full bg-accent-subtle text-xs font-semibold text-accent"
        >
          {me?.user.email.slice(0, 1).toUpperCase() ?? "?"}
        </div>
      </div>
    </header>
  );
}
