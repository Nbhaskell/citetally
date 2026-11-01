import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";

export type Load<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T }
  | { kind: "error"; error: ApiError };

interface Settled<T> {
  key: string;
  result: { data: T } | { error: ApiError };
  last: T | undefined; // the most recent good answer for any key, kept through later errors
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(error instanceof Error ? error.message : "Something went wrong.", "unknown");
}

/**
 * Load something when `key` changes, and again on `reload()` or every `pollMs` while `poll` is
 * true. While it reloads, the earlier data stays on screen (no flicker); a different `key`
 * shows "loading" until its own answer arrives.
 */
export function useApi<T>(
  key: string,
  load: (signal: AbortSignal) => Promise<T>,
  options: { pollMs?: number; poll?: boolean } = {},
): { load: Load<T>; reload: () => void; refreshing: boolean; last: T | undefined } {
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const [version, setVersion] = useState(0);
  const loader = useRef(load);
  useEffect(() => {
    loader.current = load;
  });

  useEffect(() => {
    const controller = new AbortController();
    loader.current(controller.signal).then(
      (data) => setSettled({ key, result: { data }, last: data }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setSettled((before) => ({
          key,
          result: { error: asApiError(error) },
          last: before?.last,
        }));
      },
    );
    return () => controller.abort();
  }, [key, version]);

  const { poll, pollMs } = options;
  useEffect(() => {
    if (!poll || !pollMs) return;
    const timer = window.setInterval(() => setVersion((v) => v + 1), pollMs);
    return () => window.clearInterval(timer);
  }, [poll, pollMs]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  let state: Load<T> = { kind: "loading" };
  if (settled && settled.key === key) {
    state =
      "data" in settled.result
        ? { kind: "ready", data: settled.result.data }
        : { kind: "error", error: settled.result.error };
  }
  return {
    load: state,
    reload,
    refreshing: settled !== null && settled.key !== key,
    last: settled?.last,
  };
}
