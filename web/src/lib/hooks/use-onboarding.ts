"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api/client";
import type { OnboardingState } from "@/lib/api/types";

export const ONBOARDING_QUERY_KEY = ["onboarding"] as const;

const BASE = "/api/v1/onboarding";

/**
 * Where this customer has got to (PRD section 25).
 *
 * The server derives it from the records rather than storing a counter, so
 * this is the only thing the wizard needs to decide what to show — and it
 * cannot disagree with what is actually set up.
 *
 * It polls only while the website analysis is running. That step is a crawl
 * and a model call taking tens of seconds, and it is the moment the customer
 * is deciding whether any of this works; every other step changes only when
 * they do something, so polling then would be noise.
 */
export function useOnboarding({ enabled = true }: { enabled?: boolean } = {}) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ONBOARDING_QUERY_KEY,
    queryFn: () => apiFetch<OnboardingState>(BASE),
    enabled,
    refetchInterval: (q) =>
      q.state.data?.steps.some((step) => step.state === "running") ? 2500 : false,
  });

  const finish = useMutation({
    mutationFn: () => apiFetch<OnboardingState>(BASE, { method: "POST" }),
    onSuccess: (state) => queryClient.setQueryData(ONBOARDING_QUERY_KEY, state),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ONBOARDING_QUERY_KEY });

  return { ...query, state: query.data, finish, refresh };
}
