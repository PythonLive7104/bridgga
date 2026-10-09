"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch, type Paginated } from "@/lib/api/client";
import type { Prospect, ProspectFacets, SavedSearch } from "@/lib/api/types";

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
