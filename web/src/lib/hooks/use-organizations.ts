"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api/client";
import type { Organization } from "@/lib/api/types";
import { ME_QUERY_KEY } from "@/lib/hooks/use-session";

export interface CreateOrganizationInput {
  name: string;
  country?: string;
  default_currency?: string;
  timezone?: string;
  website?: string;
}

/**
 * Creating an organization is the one write a user can make before they have
 * one, so it does not go through the tenant-scoped client path.
 *
 * The session is invalidated on success because `/me` is what supplies the
 * active organization and the capability list that decides which navigation
 * renders. Without that, the app would hold a membership the sidebar has
 * never heard of.
 */
export function useCreateOrganization() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateOrganizationInput) =>
      apiFetch<Organization>("/api/v1/organizations", {
        method: "POST",
        body: input,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  });
}
