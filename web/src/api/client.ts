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
export type DocumentDetail = Schemas["DocumentDetail"];
export type DocumentOut = Schemas["DocumentOut"];
export type EntryOut = Schemas["EntryOut"];
export type EntryPatch = Schemas["EntryPatch"];
export type EntryLine = Schemas["EntryLine"];
export type Evidence = Schemas["Evidence"];
export type CheckOut = Schemas["CheckOut"];
export type PageOut = Schemas["PageOut"];
export type VendorOut = Schemas["VendorOut"];
export type VendorSuggestion = Schemas["VendorSuggestion"];
export type Override = Schemas["Override"];
export type DecisionResponse = Schemas["DecisionResponse"];
export type CategoryOut = Schemas["CategoryOut"];
export type ExportOut = Schemas["ExportOut"];
export type ExportPreview = Schemas["ExportPreview"];
export type ExportCreated = Schemas["ExportCreated"];
export type ExportProfile = Schemas["ExportProfile"];
export type InsightsOut = Schemas["InsightsOut"];
export type SettingsOut = Schemas["SettingsOut"];
export type SettingsUpdate = Schemas["SettingsUpdate"];
export type SelfTestOut = Schemas["SelfTestOut"];

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

function send<T>(method: "PATCH" | "PUT", path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  document: (id: number, signal?: AbortSignal) =>
    request<DocumentDetail>(`/api/documents/${id}`, { signal }),
  editEntry: (entryId: number, patch: EntryPatch) =>
    send<DocumentDetail>("PATCH", `/api/entries/${entryId}`, patch),
  chooseVendor: (entryId: number, choice: { vendor_id: number } | { create: true; name?: string }) =>
    post<DocumentDetail>(
      `/api/entries/${entryId}/vendor`,
      "create" in choice ? choice : { vendor_id: choice.vendor_id, create: false },
    ),
  vendorSuggestions: (entryId: number, signal?: AbortSignal) =>
    request<VendorSuggestion[]>(`/api/entries/${entryId}/vendor-suggestions`, { signal }),
  vendors: (signal?: AbortSignal) => request<VendorOut[]>("/api/vendors", { signal }),
  categories: (signal?: AbortSignal) => request<CategoryOut[]>("/api/categories", { signal }),
  createVendor: (name: string, defaultCategory: string | null) =>
    post<VendorOut>("/api/vendors", { name, default_category: defaultCategory }),
  setVendorCategory: (id: number, defaultCategory: string | null) =>
    send<VendorOut>("PATCH", `/api/vendors/${id}`, { default_category: defaultCategory }),
  addAlias: (id: number, alias: string) => post<VendorOut>(`/api/vendors/${id}/aliases`, { alias }),
  mergeVendor: (id: number, into: number) => post<VendorOut>(`/api/vendors/${id}/merge`, { into }),
  exportPreview: (profile: ExportProfile, includeExported: boolean, signal?: AbortSignal) =>
    request<ExportPreview>(
      `/api/exports/preview?profile=${profile}&include_exported=${includeExported}`,
      { signal },
    ),
  createExport: (profile: ExportProfile, includeExported: boolean) =>
    post<ExportCreated>("/api/exports", { profile, include_exported: includeExported }),
  exports: (signal?: AbortSignal) => request<ExportOut[]>("/api/exports", { signal }),
  insights: (from: string | null, to: string | null, signal?: AbortSignal) => {
    const params = new URLSearchParams();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    const text = params.toString();
    return request<InsightsOut>(`/api/insights${text ? `?${text}` : ""}`, { signal });
  },
  settings: (signal?: AbortSignal) => request<SettingsOut>("/api/settings", { signal }),
  updateSettings: (patch: SettingsUpdate) => send<SettingsOut>("PATCH", "/api/settings", patch),
  selfTest: () => post<SelfTestOut>("/api/self-test"),
  approve: (id: number, overrides: Override[], reviewSeconds?: number) =>
    post<DecisionResponse>(`/api/documents/${id}/approve`, {
      overrides,
      review_seconds: reviewSeconds ?? null,
    }),
  reject: (id: number, reason: string, reviewSeconds?: number) =>
    post<DecisionResponse>(`/api/documents/${id}/reject`, {
      reason,
      review_seconds: reviewSeconds ?? null,
    }),
  reopen: (id: number) => post<DecisionResponse>(`/api/documents/${id}/reopen`, {}),
  markDuplicate: (id: number, duplicateOf: number, reviewSeconds?: number) =>
    post<DecisionResponse>(`/api/documents/${id}/mark-duplicate`, {
      duplicate_of: duplicateOf,
      review_seconds: reviewSeconds ?? null,
    }),
};

// Kept for the one caller that predates the typed client.
export const fetchStatus = api.status;
