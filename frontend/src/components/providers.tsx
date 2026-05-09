"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ProjectProvider } from "@/lib/project/context";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1_000,        // 1 phút — tránh over-fetch
            gcTime: 5 * 60 * 1_000,       // 5 phút garbage collection
            refetchOnWindowFocus: false,   // tránh fetch surprise khi user tab back
            retry: (failureCount, error) => {
              // Không retry 4xx (client error) — chỉ retry 5xx (server error)
              const status = (error as { status?: number })?.status;
              if (status && status < 500) return false;
              return failureCount < 2;
            },
          },
          mutations: {
            retry: false, // mutations không retry — side effects đã xảy ra
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ProjectProvider>
        {children}
      </ProjectProvider>
    </QueryClientProvider>
  );
}
