import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ExportOut, ExportPreview } from "../api/client";
import { ToastProvider } from "../ui/Toast";
import Exports from "./Exports";

const PREVIEW: ExportPreview = {
  entry_count: 3,
  row_count: 3,
  totals: { USD: "1240.05" },
  first_date: "2026-03-02",
  last_date: "2026-03-28",
  skipped_already_exported: 0,
  columns: ["Date", "Vendor", "Total"],
  sample: [
    ["2026-03-02", "Northfield Pet Supply Co.", "152.00"],
    ["2026-03-09", "=HYPERLINK(x)", "-45.50"],
  ],
};

const FILE: ExportOut = {
  id: 4,
  profile: "entries_csv",
  entry_count: 3,
  row_count: 3,
  file_name: "citetally-export-4.csv",
  file_sha256: "a".repeat(64),
  created_at: "2026-03-30T10:15:00.000Z",
  download_url: "/api/exports/4/download",
};

interface Seen {
  method: string;
  path: string;
  body: unknown;
}

function install(preview: ExportPreview, history: ExportOut[] = [], reply: (seen: Seen) => Response | undefined = () => undefined) {
  const seen: Seen[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
      const call = { method, path, body };
      seen.push(call);
      const custom = reply(call);
      if (custom) return custom;
      if (path.startsWith("/api/exports/preview")) return Response.json(preview);
      if (path === "/api/exports" && method === "GET") return Response.json(history);
      if (path === "/api/exports" && method === "POST") {
        return Response.json({ export: FILE, skipped_already_exported: 0 }, { status: 201 });
      }
      return new Response("no", { status: 404 });
    }),
  );
  return seen;
}

function renderPage() {
  return render(
    <ToastProvider>
      <Exports />
    </ToastProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Exports", () => {
  it("says what is ready: count, total, dates, rows and the first rows of the file", async () => {
    install(PREVIEW);
    renderPage();
    expect(await screen.findByText("Ready to export: 3 approved entries")).toBeInTheDocument();
    const ready = screen.getByRole("region", { name: "Ready to export" });
    expect(ready).toHaveTextContent("$1,240.05");
    expect(ready).toHaveTextContent("2 Mar 2026 to 28 Mar 2026");
    const sample = within(ready).getByRole("table", { name: "The first rows of the file" });
    expect(within(sample).getByText("Vendor")).toBeInTheDocument();
    expect(within(sample).getByText("=HYPERLINK(x)")).toBeInTheDocument(); // text, not a link or formula
    expect(screen.getByText("No exports yet. Files you make will be listed here so you can download them again.")).toBeInTheDocument();
  });

  it("shows a credit total with a minus sign", async () => {
    install({ ...PREVIEW, totals: { USD: "-45.50" } });
    renderPage();
    expect(await screen.findByRole("region", { name: "Ready to export" })).toHaveTextContent("−$45.50");
  });

  it("asks for the preview again when the row type changes", async () => {
    const seen = install(PREVIEW);
    renderPage();
    await screen.findByText("Ready to export: 3 approved entries");
    fireEvent.click(screen.getByRole("radio", { name: /One row per line item/ }));
    await waitFor(() =>
      expect(seen.some((s) => s.path === "/api/exports/preview?profile=lines_csv&include_exported=false")).toBe(true),
    );
  });

  it("warns before already exported entries are included, in words", async () => {
    const seen = install(PREVIEW);
    renderPage();
    await screen.findByText("Ready to export: 3 approved entries");
    expect(screen.queryByText(/Importing them again can create duplicates/)).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "Include entries I've already exported" }));
    expect(await screen.findByText(/Importing them again can create duplicates/)).toBeInTheDocument();
    await waitFor(() => expect(seen.some((s) => s.path.endsWith("include_exported=true"))).toBe(true));
  });

  it("explains when nothing is ready, and when everything was already exported", async () => {
    install({ ...PREVIEW, entry_count: 0, row_count: 0, totals: {}, first_date: null, last_date: null, sample: [] });
    renderPage();
    expect(await screen.findByText("Nothing is ready to export")).toBeInTheDocument();
    expect(screen.getByText(/Approve entries in the Inbox/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export approved entries" })).toBeNull();
    cleanup();
    install({ ...PREVIEW, entry_count: 0, row_count: 0, totals: {}, sample: [], skipped_already_exported: 2 });
    renderPage();
    expect(await screen.findByText(/2 approved entries have already been exported/)).toBeInTheDocument();
  });

  it("confirms, then exports, offers the download and updates the history", async () => {
    let made = false;
    const seen = install(PREVIEW, [], (call) => {
      if (call.method === "POST") made = true;
      if (call.path === "/api/exports" && call.method === "GET" && made) return Response.json([FILE]);
      return undefined;
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Export approved entries" }));
    const dialog = screen.getByRole("dialog", { name: "Export these entries?" });
    expect(dialog).toHaveTextContent("Nothing is sent anywhere");
    expect(seen.some((s) => s.method === "POST")).toBe(false); // not yet
    fireEvent.click(within(dialog).getByRole("button", { name: "Export 3 entries" }));
    const link = await screen.findByRole("link", { name: "Download citetally-export-4.csv" });
    expect(link).toHaveAttribute("href", "/api/exports/4/download");
    expect(seen.find((s) => s.method === "POST")?.body).toEqual({ profile: "entries_csv", include_exported: false });
    const history = await screen.findByRole("table", { name: "Earlier exports" });
    expect(within(history).getByText("aaaaaaaaaaaa")).toBeInTheDocument();
    expect(within(history).getByRole("link", { name: "Download again" })).toHaveAttribute("href", "/api/exports/4/download");
    expect(within(history).getByText("One row per entry")).toBeInTheDocument();
  });

  it("shows the reason when the export is refused, and keeps the page usable", async () => {
    install(PREVIEW, [], (call) =>
      call.method === "POST"
        ? Response.json({ error: { code: "nothing_to_export", message: "There is nothing to export.", request_id: "r" } }, { status: 409 })
        : undefined,
    );
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Export approved entries" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Export 3 entries" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("There is nothing to export.");
    expect(screen.queryByRole("link", { name: /Download citetally/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Export approved entries" })).toBeEnabled();
  });
});
