"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, type Paginated } from "@/lib/api/client";
import type { ICP, ICPField } from "@/lib/api/types";

export const ICP_QUERY_KEY = ["icps"] as const;

const BASE = "/api/v1/intelligence/icps";

/**
 * Every ICP for the organization, with the mutations that change them.
 *
 * Generation is synchronous on the server, unlike the company analysis: it
 * fetches nothing and makes one model call, so it returns the finished record
 * rather than queueing and leaving the client to poll.
 */
export function useICPs() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ICP_QUERY_KEY,
    queryFn: () => apiFetch<Paginated<ICP>>(BASE),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ICP_QUERY_KEY });

  const generate = useMutation({
    mutationFn: () => apiFetch<ICP>(`${BASE}/generate`, { method: "POST" }),
    onSuccess: refresh,
  });

  const regenerate = useMutation({
    mutationFn: (id: string) =>
      apiFetch<ICP>(`${BASE}/${id}/regenerate`, { method: "POST" }),
    onSuccess: refresh,
  });

  const save = useMutation({
    mutationFn: ({
      id,
      changes,
    }: {
      id: string;
      changes: Partial<Record<ICPField, unknown>>;
    }) => apiFetch<ICP>(`${BASE}/${id}`, { method: "PATCH", body: changes }),
    onSuccess: refresh,
  });

  const reset = useMutation({
    mutationFn: ({ id, fields }: { id: string; fields: ICPField[] }) =>
      apiFetch<ICP>(`${BASE}/${id}/reset`, { method: "POST", body: { fields } }),
    onSuccess: refresh,
  });

  const activate = useMutation({
    mutationFn: (id: string) =>
      apiFetch<ICP>(`${BASE}/${id}/activate`, { method: "POST" }),
    onSuccess: refresh,
  });

  const icps = query.data?.results ?? [];

  return {
    ...query,
    icps,
    active: icps.find((icp) => icp.is_active) ?? null,
    generate,
    regenerate,
    save,
    reset,
    activate,
  };
}
