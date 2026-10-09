"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, type Paginated } from "@/lib/api/client";
import type { MarketRecommendation } from "@/lib/api/types";

export const MARKETS_QUERY_KEY = ["markets"] as const;

const BASE = "/api/v1/intelligence/markets";

/**
 * The market ranking, and the selection made from it.
 *
 * Those are two different things and the API keeps them apart: the ranking is
 * advice, the selection is a decision, and everything downstream reads the
 * decision. The hook mirrors that rather than letting a click on a card look
 * like it changed the recommendation.
 */
export function useMarkets() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: MARKETS_QUERY_KEY,
    queryFn: () => apiFetch<Paginated<MarketRecommendation>>(BASE),
  });

  const absorb = (rows: MarketRecommendation[]) =>
    queryClient.setQueryData(MARKETS_QUERY_KEY, (current: unknown) => ({
      ...(current ?? {}),
      results: rows,
    }));

  const recommend = useMutation({
    mutationFn: (includeInternational: boolean) =>
      apiFetch<MarketRecommendation[]>(`${BASE}/recommend`, {
        method: "POST",
        body: { include_international: includeInternational },
      }),
    onSuccess: absorb,
  });

  const select = useMutation({
    mutationFn: (codes: string[]) =>
      apiFetch<MarketRecommendation[]>(`${BASE}/select`, {
        method: "POST",
        body: { codes },
      }),
    onSuccess: absorb,
  });

  const markets = query.data?.results ?? [];

  return {
    ...query,
    markets,
    selected: markets.filter((market) => market.is_selected),
    recommend,
    select,
  };
}
