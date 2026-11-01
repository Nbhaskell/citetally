import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, queryString, UNREACHABLE } from "./client";

afterEach(() => vi.unstubAllGlobals());

function stub(response: Response | Error) {
  const fetchMock = vi.fn(async () => {
    if (!(response instanceof Response)) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("queryString", () => {
  it("builds repeated statuses and leaves out what is empty", () => {
    expect(queryString({})).toBe("");
    expect(
      queryString({ statuses: ["received", "needs_review"], check: "", q: "  ", batch: "", order: "oldest" }),
    ).toBe("?status=received&status=needs_review&order=oldest");
  });

  it("trims and encodes the search text", () => {
    expect(queryString({ q: " a&b c ", check: "LINE_MATH", limit: 50, cursor: "9" })).toBe(
      "?check=LINE_MATH&q=a%26b+c&cursor=9&limit=50",
    );
  });
});

describe("api errors", () => {
  it("reads the one error shape the API uses", async () => {
    stub(
      Response.json(
        { error: { code: "approval_blocked", message: "Blocking checks.", request_id: "abc123", details: { unresolved: ["TOTAL_MATCH"] } } },
        { status: 409 },
      ),
    );
    const error = await api.counts().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    const api_error = error as ApiError;
    expect(api_error.message).toBe("Blocking checks.");
    expect(api_error.code).toBe("approval_blocked");
    expect(api_error.status).toBe(409);
    expect(api_error.requestId).toBe("abc123");
    expect(api_error.details).toEqual({ unresolved: ["TOTAL_MATCH"] });
  });

  it("copes with an error that is not JSON", async () => {
    stub(new Response("<html>gateway</html>", { status: 502, headers: { "x-request-id": "r1" } }));
    const error = (await api.counts().catch((e: unknown) => e)) as ApiError;
    expect(error.message).toBe("The API answered with status 502.");
    expect(error.requestId).toBe("r1");
    expect(error.message).not.toContain("gateway");
  });

  it("says plainly when the API cannot be reached", async () => {
    stub(new TypeError("Failed to fetch"));
    const error = (await api.status().catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe(UNREACHABLE);
    expect(error.message).toContain("python -m citetally");
  });

  it("lets an aborted request stay an abort", async () => {
    stub(new DOMException("aborted", "AbortError"));
    const error = await api.status().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(DOMException);
  });
});

describe("api calls", () => {
  it("sends files as a form with the batch label", async () => {
    const fetchMock = stub(Response.json({ results: [] }));
    await api.upload([new File(["x"], "a.pdf")], "Upload 1");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/documents");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect((form.get("files") as File).name).toBe("a.pdf");
    expect(form.get("batch_label")).toBe("Upload 1");
  });

  it("sends reprocess as JSON", async () => {
    const fetchMock = stub(Response.json({}));
    await api.reprocess(7, "extract");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/documents/7/reprocess");
    expect(JSON.parse(init.body as string)).toEqual({ from_stage: "extract" });
  });
});
