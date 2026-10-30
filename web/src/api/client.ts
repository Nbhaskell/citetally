import type { components } from "./schema";

export type StatusResponse = components["schemas"]["StatusResponse"];

export async function fetchStatus(signal?: AbortSignal): Promise<StatusResponse> {
  const response = await fetch("/api/status", { signal });
  if (!response.ok) {
    throw new Error(`The API answered with status ${response.status}.`);
  }
  return (await response.json()) as StatusResponse;
}
