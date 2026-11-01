import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
  database_ok: true,
  ocr_available: true,
  queue_depth: 0,
  last_model_call_at: null,
};

const ZERO = {
  received: 0, read: 0, extracted: 0, needs_review: 0, approved: 0, rejected: 0, exported: 0,
  failed: 0, duplicate: 0,
};  // prettier-ignore

function install(current: () => StatusResponse | Error) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith("/api/status")) {
      const value = current();
      if (value instanceof Error) throw value;
      return Response.json(value);
    }
    if (path.startsWith("/api/documents/counts")) return Response.json({ counts: ZERO, batches: [] });
    if (/^\/api\/documents\/\d+$/.test(path)) {
      return Response.json({ error: { code: "not_found", message: "Document 12 was not found.", request_id: "t" } }, { status: 404 });
    }
    if (path.startsWith("/api/documents")) return Response.json({ items: [], next_cursor: null });
    return new Response("no", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  window.location.hash = "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the frame", () => {
  it("shows the Inbox, the places you can go, and the demo label", async () => {
    install(() => status);
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Inbox" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const name of ["Inbox", "Vendors", "Exports", "Insights", "Settings"]) {
      expect(nav).toHaveTextContent(name);
    }
    expect(screen.getByRole("link", { name: "Inbox" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Demo data. All vendors, invoices and amounts are invented.")).toBeInTheDocument();
    expect(document.title).toBe("Inbox – Citetally");
  });

  it("leaves the label off when the data is not synthetic", async () => {
    install(() => ({ ...status, synthetic_data: false }));
    render(<App />);
    await screen.findByRole("heading", { name: "Inbox" });
    expect(screen.queryByText(/Demo data/)).toBeNull();
  });

  it("shows a hosted-mode banner that cannot be dismissed", async () => {
    install(() => ({ ...status, hosted_mode: true, model_provider: "hosted" }));
    render(<App />);
    const banner = await screen.findByText(/Hosted model mode: page content is sent to the hosted provider/);
    expect(banner.closest("[role=status]")).not.toBeNull();
    expect(screen.queryByRole("button", { name: /dismiss|close/i })).toBeNull();
  });

  it("says plainly when the text reader is missing", async () => {
    install(() => ({ ...status, ocr_available: false }));
    render(<App />);
    expect(await screen.findByText(/Tesseract\) was not found/)).toBeInTheDocument();
  });

  it("explains how to start the app when it cannot be reached, and tries again on request", async () => {
    let up = false;
    const fetchMock = install(() => (up ? status : new TypeError("Failed to fetch")));
    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Cannot reach Citetally");
    expect(alert).toHaveTextContent("python -m citetally");
    up = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Inbox" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
  });

  it("keeps the screen and warns when contact is lost later", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout"] });
    let down = false;
    install(() => (down ? new TypeError("Failed to fetch") : status));
    render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByRole("heading", { name: "Inbox" })).toBeInTheDocument();
    down = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_100);
    });
    expect(screen.getByText(/Lost contact with Citetally/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Inbox" })).toBeInTheDocument();
  });
});

describe("moving between screens", () => {
  it("shows a place for every link and moves keyboard focus to the new screen", async () => {
    install(() => status);
    render(<App />);
    await screen.findByRole("heading", { name: "Inbox" });
    act(() => {
      window.location.hash = "#/vendors";
    });
    expect(await screen.findByRole("heading", { name: "Vendors" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Vendors" })).toHaveAttribute("aria-current", "page");
    expect(document.title).toBe("Vendors – Citetally");
    await waitFor(() => expect(screen.getByRole("main")).toHaveFocus());
  });

  it("keeps Inbox marked as current while a document is open", async () => {
    install(() => status);
    window.location.hash = "#/review/12";
    render(<App />);
    // The test server has no such document, so the Review screen says so plainly.
    expect(await screen.findByText("That document does not exist")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Inbox" })[0]).toHaveAttribute("aria-current", "page");
  });

  it("does not break on an address it does not know", async () => {
    install(() => status);
    window.location.hash = "#/nope";
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Not found" })).toBeInTheDocument();
  });

  it("has a way to skip the frame", async () => {
    install(() => status);
    render(<App />);
    await screen.findByRole("heading", { name: "Inbox" });
    expect(screen.getByRole("link", { name: "Skip to the content" })).toHaveAttribute("href", "#main");
  });
});
