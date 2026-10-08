"use client";

import { providerRedirectUrl } from "@/lib/api/auth";

/**
 * OAuth entry points.
 *
 * These are plain links, not fetch calls: the provider handshake is a
 * top-level navigation, and attempting it from fetch would be blocked by the
 * provider's framing and CORS rules.
 */
export function SocialAuthButtons({ disabled }: { disabled?: boolean }) {
  return (
    <div className="grid gap-2">
      {(
        [
          { provider: "google", label: "Continue with Google" },
          { provider: "microsoft", label: "Continue with Microsoft" },
        ] as const
      ).map(({ provider, label }) => (
        <a
          key={provider}
          href={disabled ? undefined : providerRedirectUrl(provider)}
          aria-disabled={disabled || undefined}
          className="inline-flex h-10 items-center justify-center rounded-[var(--radius-control)] border border-border bg-surface px-4 text-sm font-medium text-fg transition-colors hover:border-border-strong aria-disabled:pointer-events-none aria-disabled:opacity-50"
        >
          {label}
        </a>
      ))}
    </div>
  );
}
