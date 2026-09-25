import { useEffect } from "react";
import type { SetURLSearchParams } from "react-router-dom";

/** Fill an absent selection from the server's newest-first list, without adding history. */
export function useLatestRun(
  params: URLSearchParams,
  setParams: SetURLSearchParams,
  latestId: string | undefined,
  ready: boolean,
) {
  useEffect(() => {
    if (params.has("run_id") || !ready || !latestId) return;
    setParams(
      (current) => {
        // A selection made while the list was loading always takes precedence.
        if (current.has("run_id")) return current;
        const next = new URLSearchParams(current);
        next.set("run_id", latestId);
        return next;
      },
      { replace: true },
    );
  }, [params, setParams, latestId, ready]);
}
