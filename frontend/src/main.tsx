import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "./lib/api";
import { AuthProvider } from "./auth";
import { App } from "./App";
import "./styles.css";
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10000,
      retry: (count, error) =>
        count < 1 && (!(error instanceof ApiError) || error.status >= 500),
    },
    mutations: { retry: false },
  },
});
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
