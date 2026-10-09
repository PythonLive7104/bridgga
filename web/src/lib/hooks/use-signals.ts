"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch, type Paginated } from "@/lib/api/client";
import type { LeadSignal, SignalSummary } from "@/lib/api/types";

export const SIGNALS_QUERY_KEY = ["signals"] as const;

export interface SignalQuery {
  type?: string[];
  company?: string;
  days?: number;
  include_expired?: boolean;
}

function toParams(query: SignalQuery): Record<string, string> {
  const params: Record<string, string> = {};
  if (query.type?.length) params.type = query.type.join(",");
  if (query.company) params.company = query.company;
  if (query.days) params.days = String(query.days);
  if (query.include_expired) params.include_expired = "true";
  return params;
}

export function useSignals(query: SignalQuery = {}) {
  const result = useQuery({
    queryKey: [...SIGNALS_QUERY_KEY, query],
    queryFn: () =>
      apiFetch<Paginated<LeadSignal> & { count: number }>("/api/v1/signals", {
        searchParams: toParams(query),
      }),
    placeholderData: keepPreviousData,
  });

  return {
    ...result,
    signals: result.data?.results ?? [],
    total: result.data?.count ?? 0,
  };
}

export function useSignalSummary() {
  return useQuery({
    queryKey: [...SIGNALS_QUERY_KEY, "summary"],
    queryFn: () => apiFetch<SignalSummary>("/api/v1/signals/summary"),
    staleTime: 60_000,
  });
}

export function useDismissSignal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      apiFetch<LeadSignal>(`/api/v1/signals/${id}/dismiss`, {
        method: "POST",
        body: { reason: reason ?? "" },
      }),
    // The prospect table shows a company's best live signal, so dismissing one
    // there changes a row here too.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SIGNALS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: ["prospects"] });
    },
  });
}
