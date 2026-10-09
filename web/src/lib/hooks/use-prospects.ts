"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch, type Paginated } from "@/lib/api/client";
import type {
  Prospect,
  ProspectFacets,
  ProspectResearch,
  SavedSearch,
  ScoreExplanation,
  ScoringProfile,
} from "@/lib/api/types";

export const PROSPECTS_QUERY_KEY = ["prospects"] as const;
export const SAVED_SEARCHES_QUERY_KEY = ["saved-searches"] as const;

/** Filter state, matching the server's section 29 parameter names. */
export interface ProspectQuery {
  q?: string;
  country?: string[];
  industry?: string[];
  employee_range?: string[];
  signal?: string[];
  has_contact?: boolean;
  contactable?: boolean;
  min_score?: number;
}

function toParams(query: ProspectQuery): Record<string, string> {
  const params: Record<string, string> = {};
  if (query.q) params.q = query.q;
  // Comma-joined rather than repeated keys: the server accepts both, and this
  // keeps the query key stable and the URL readable.
  for (const key of ["country", "industry", "employee_range", "signal"] as const) {
    const values = query[key];
    if (values?.length) params[key] = values.join(",");
  }
  if (query.has_contact !== undefined) params.has_contact = String(query.has_contact);
  if (query.contactable) params.contactable = "true";
  if (query.min_score) params.min_score = String(query.min_score);
  return params;
}

export function useProspects(query: ProspectQuery) {
  const result = useQuery({
    queryKey: [...PROSPECTS_QUERY_KEY, query],
    queryFn: () =>
      apiFetch<Paginated<Prospect> & { search_backend: string }>("/api/v1/prospects", {
        searchParams: toParams(query),
      }),
    // Keeps the previous page on screen while the next loads, so typing in the
    // search box does not blank the table on every keystroke.
    placeholderData: keepPreviousData,
  });

  return {
    ...result,
    prospects: result.data?.results ?? [],
    searchBackend: result.data?.search_backend ?? "",
  };
}

export function useProspectFacets() {
  return useQuery({
    queryKey: [...PROSPECTS_QUERY_KEY, "facets"],
    queryFn: () => apiFetch<ProspectFacets>("/api/v1/prospects/facets"),
    staleTime: 60_000,
  });
}

export function useSavedSearches() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: SAVED_SEARCHES_QUERY_KEY,
    queryFn: () => apiFetch<Paginated<SavedSearch>>("/api/v1/saved-searches"),
  });

  const save = useMutation({
    // The filters are stored as the ProspectQuery shape the table uses, so a
    // saved search loads straight back into the controls that produced it.
    mutationFn: (payload: { name: string; filters: ProspectQuery; is_shared: boolean }) =>
      apiFetch<SavedSearch>("/api/v1/saved-searches", { method: "POST", body: payload }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: SAVED_SEARCHES_QUERY_KEY }),
  });

  return { ...query, searches: query.data?.results ?? [], save };
}

export const SCORING_QUERY_KEY = ["scoring-profile"] as const;

/**
 * Why a prospect scores what it scores (PRD sections 32, 119).
 *
 * Fetched per prospect, only when the panel is open: the explanation is
 * several times the size of the row it explains, and a list of fifty would
 * otherwise carry fifty of them nobody asked for.
 */
export function useProspectScore(prospectId: string | null) {
  return useQuery({
    queryKey: [...PROSPECTS_QUERY_KEY, "score", prospectId],
    queryFn: () => apiFetch<ScoreExplanation>(`/api/v1/prospects/${prospectId}/score`),
    enabled: Boolean(prospectId),
  });
}

/** The configurable section 32 weighting. */
export function useScoringProfile() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: SCORING_QUERY_KEY,
    queryFn: () => apiFetch<ScoringProfile>("/api/v1/scoring/profile"),
    staleTime: 60_000,
  });

  // Changing the weighting rescores every stored lead on the server, so both
  // the profile and the list that is sorted by it are invalidated.
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: SCORING_QUERY_KEY });
    void queryClient.invalidateQueries({ queryKey: PROSPECTS_QUERY_KEY });
  };

  const update = useMutation({
    mutationFn: (weights: Record<string, number>) =>
      apiFetch<ScoringProfile>("/api/v1/scoring/profile", {
        method: "PATCH",
        body: { weights },
      }),
    onSuccess: invalidate,
  });

  const reset = useMutation({
    mutationFn: () =>
      apiFetch<ScoringProfile>("/api/v1/scoring/profile", { method: "DELETE" }),
    onSuccess: invalidate,
  });

  return { ...query, profile: query.data, update, reset };
}

/**
 * The sales brief for one prospect (PRD sections 34, 35).
 *
 * `retry: false` because a 404 here is the normal state, not a failure: most
 * prospects have not been researched, and retrying would turn "nothing yet"
 * into three requests and a spinner.
 */
export function useProspectResearch(prospectId: string | null) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: [...PROSPECTS_QUERY_KEY, "research", prospectId],
    queryFn: () => apiFetch<ProspectResearch>(`/api/v1/prospects/${prospectId}/research`),
    enabled: Boolean(prospectId),
    retry: false,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: [...PROSPECTS_QUERY_KEY, "research", prospectId],
    });
    // The reason-to-contact is on the row too.
    void queryClient.invalidateQueries({ queryKey: PROSPECTS_QUERY_KEY });
  };

  const request = useMutation({
    mutationFn: () =>
      apiFetch<{ status: string }>(`/api/v1/prospects/${prospectId}/research`, {
        method: "POST",
      }),
    // Queued server-side, so there is nothing to show yet; the panel polls on
    // the next open rather than pretending to stream.
    onSuccess: invalidate,
  });

  const edit = useMutation({
    mutationFn: (data: Partial<ProspectResearch>) =>
      apiFetch<ProspectResearch>(`/api/v1/prospects/${prospectId}/research`, {
        method: "PATCH",
        body: data,
      }),
    onSuccess: invalidate,
  });

  return { ...query, research: query.data, request, edit };
}
