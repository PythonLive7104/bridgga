"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api/client";
import type { Me } from "@/lib/api/types";

export const ME_QUERY_KEY = ["me"] as const;

/**
 * Identity, organization memberships and the active role in one request.
 *
 * `capabilities` drives which navigation items and actions render. It is a UI
 * convenience only -- the server re-checks every capability on every request,
 * so hiding a button is never the access control.
 */
export function useSession() {
  const query = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: () => apiFetch<Me>("/api/v1/me"),
    staleTime: 60_000,
  });

  const can = (capability: string): boolean =>
    query.data?.active_capabilities.includes(capability) ?? false;

  return {
    ...query,
    me: query.data,
    organization: query.data?.active_organization ?? null,
    role: query.data?.active_role ?? null,
    /** True when the user belongs to several orgs and has not chosen one. */
    needsOrganizationChoice:
      !!query.data &&
      !query.data.active_organization &&
      query.data.memberships.length > 1,
    /** True when the user has no organization at all and must create one. */
    needsOnboarding: !!query.data && query.data.memberships.length === 0,
    can,
  };
}
