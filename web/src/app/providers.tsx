"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";

import { ApiError } from "@/lib/api/client";

export function Providers({ children }: { children: React.ReactNode }) {
  // Created in state so each browser session gets exactly one client, and so
  // a server render never shares a cache between users.
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (failureCount, error) => {
              // Retrying an auth, permission or validation failure cannot
              // succeed and only multiplies the audit noise.
              if (error instanceof ApiError && error.status < 500) return false;
              return failureCount < 2;
            },
            refetchOnWindowFocus: false,
          },
          mutations: { retry: false },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
