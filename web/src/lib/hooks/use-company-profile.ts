"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api/client";
import type { CompanyProfile, CompanyProfileField } from "@/lib/api/types";

export const COMPANY_PROFILE_QUERY_KEY = ["company-profile"] as const;

const BASE = "/api/v1/intelligence/company-profile";

/**
 * The organization's company profile, with the mutations that edit it.
 *
 * Analysis is queued on the server -- it crawls several pages and makes an
 * advanced-tier model call, far longer than a request should stay open -- so
 * this polls while the status is `analyzing` and stops as soon as it is not.
 * Polling only in that state keeps an idle dashboard quiet.
 */
export function useCompanyProfile() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: COMPANY_PROFILE_QUERY_KEY,
    queryFn: () => apiFetch<CompanyProfile>(BASE),
    refetchInterval: (q) => (q.state.data?.status === "analyzing" ? 2500 : false),
  });

  /** Replace the cache from a mutation response rather than refetching. */
  const absorb = (profile: CompanyProfile) => {
    queryClient.setQueryData(COMPANY_PROFILE_QUERY_KEY, profile);
  };

  const analyze = useMutation({
    mutationFn: (website?: string) =>
      apiFetch<CompanyProfile>(`${BASE}/analyze`, {
        method: "POST",
        body: website ? { website } : {},
      }),
    // The response is the profile as it was *before* the queued job runs, so
    // this invalidates rather than absorbing: the next fetch picks up the
    // `analyzing` status and the poll above takes over.
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: COMPANY_PROFILE_QUERY_KEY }),
  });

  const save = useMutation({
    mutationFn: (changes: Partial<Record<CompanyProfileField | "website", unknown>>) =>
      apiFetch<CompanyProfile>(BASE, { method: "PATCH", body: changes }),
    onSuccess: absorb,
  });

  const reset = useMutation({
    mutationFn: (fields: CompanyProfileField[]) =>
      apiFetch<CompanyProfile>(`${BASE}/reset`, { method: "POST", body: { fields } }),
    onSuccess: absorb,
  });

  const confirm = useMutation({
    mutationFn: () => apiFetch<CompanyProfile>(`${BASE}/confirm`, { method: "POST" }),
    onSuccess: absorb,
  });

  return {
    ...query,
    profile: query.data,
    isAnalyzing: query.data?.status === "analyzing" || analyze.isPending,
    analyze,
    save,
    reset,
    confirm,
  };
}
