import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { StatusResponse } from "./api/client";

const status: StatusResponse = {
  app: "citetally",
  version: "0.1.0",
  model_provider: "ollama",
  text_model: "qwen3:8b",
  vision_model: "",
  ocr_engine: "tesseract",
  hosted_mode: false,
  synthetic_data: true,
  database_ok: null,
  ocr_available: null,
  queue_depth: null,
  last_model_call_at: null,
};

function mockFetch(response: Response | Error) {
  const fetchMock = vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows the status returned by the API", async () => {
    const fetchMock = mockFetch(Response.json(status));
    render(<App />);
    expect(screen.getByText(/checking the api/i)).toBeInTheDocument();
    expect(await screen.findByText("qwen3:8b")).toBeInTheDocument();
    expect(screen.getByText("ollama")).toBeInTheDocument();
    expect(screen.getByText("tesseract")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/status", expect.anything());
  });

  it("labels the data as synthetic when the API says so", async () => {
    mockFetch(Response.json(status));
    render(<App />);
    expect(
      await screen.findByText("Demo data. All vendors, invoices and amounts are invented."),
    ).toBeInTheDocument();
  });

  it("shows a hosted-mode banner only in hosted mode", async () => {
    mockFetch(Response.json({ ...status, model_provider: "hosted", hosted_mode: true }));
    render(<App />);
    expect(await screen.findByText(/hosted model mode/i)).toBeInTheDocument();
  });

  it("does not show the hosted banner in local mode", async () => {
    mockFetch(Response.json(status));
    render(<App />);
    await screen.findByText("qwen3:8b");
    expect(screen.queryByText(/hosted model mode/i)).not.toBeInTheDocument();
  });

  it("explains how to start the API when it cannot be reached", async () => {
    mockFetch(new TypeError("Failed to fetch"));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot reach the api/i);
  });

  it("reports an error response from the API", async () => {
    mockFetch(new Response("boom", { status: 500 }));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/500/);
  });
});
