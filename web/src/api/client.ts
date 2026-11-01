import type { components } from "./schema";

type Schemas = components["schemas"];
export type StatusResponse = Schemas["StatusResponse"];
export type DocumentSummary = Schemas["DocumentSummary"];
export type DocumentList = Schemas["DocumentList"];
export type DocumentCounts = Schemas["DocumentCounts"];
export type DocumentStatus = Schemas["DocumentStatus"];
export type CheckCode = Schemas["CheckCode"];
export type UploadResponse = Schemas["UploadResponse"];
export type UploadResult = Schemas["UploadResult"];

/** Every refusal from the API has one shape: a code, a message for a person, a request id. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string | null;
  readonly details: Record<string, unknown> | null;

  constructor(
    message: string,
    code: string,
    status = 0,
    requestId: string | null = null,
    details: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.details = details;
  }
}

export const UNREACHABLE = "unreachable";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(
      "Cannot reach Citetally. Start it with: python -m citetally",
      UNREACHABLE,
    );
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      /* not JSON: fall through to the plain message */
    }
    const error = (body as { error?: Record<string, unknown> } | null)?.error;
    throw new ApiError(
      typeof error?.message === "string"
        ? error.message
        : `The API answered with status ${response.status}.`,
      typeof error?.code === "string" ? error.code : "http_error",
      response.status,
      typeof error?.request_id === "string" ? error.request_id : response.headers.get("x-request-id"),
      (error?.details as Record<string, unknown> | undefined) ?? null,
    );
  }
  return (await response.json()) as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export interface DocumentQuery {
  statuses?: DocumentStatus[];
  check?: CheckCode | "";
  q?: string;
  batch?: string;
  order?: "newest" | "oldest";
  cursor?: string | null;
  limit?: number;
}

export function queryString(query: DocumentQuery): string {
  const params = new URLSearchParams();
  for (const status of query.statuses ?? []) params.append("status", status);
  if (query.check) params.set("check", query.check);
  if (query.q?.trim()) params.set("q", query.q.trim());
  if (query.batch) params.set("batch", query.batch);
  if (query.order) params.set("order", query.order);
  if (query.cursor) params.set("cursor", query.cursor);
  if (query.limit) params.set("limit", String(query.limit));
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const api = {
  status: (signal?: AbortSignal) => request<StatusResponse>("/api/status", { signal }),
  documents: (query: DocumentQuery, signal?: AbortSignal) =>
    request<DocumentList>(`/api/documents${queryString(query)}`, { signal }),
  counts: (signal?: AbortSignal) => request<DocumentCounts>("/api/documents/counts", { signal }),
  upload: (files: File[], batchLabel?: string) => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    if (batchLabel) form.append("batch_label", batchLabel);
    return request<UploadResponse>("/api/documents", { method: "POST", body: form });
  },
  loadDemo: () => post<UploadResponse>("/api/demo/load"),
  reprocess: (id: number, fromStage: "read" | "extract") =>
    post<Schemas["DocumentOut"]>(`/api/documents/${id}/reprocess`, { from_stage: fromStage }),
};

// Kept for the one caller that predates the typed client.
export const fetchStatus = api.status;
