import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentCounts, DocumentList, DocumentSummary, UploadResponse } from "../api/client";
import { ToastProvider } from "../ui/Toast";
import Inbox from "./Inbox";

let nextId = 1;
function row(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  const id = nextId++;
  return {
    id,
    original_filename: `invoice-${id}.pdf`,
    mime_type: "application/pdf",
    source_kind: "digital_pdf",
    page_count: 1,
    size_bytes: 1000,
    status: "needs_review",
    duplicate_of: null,
    failure_stage: null,
    failure_message: null,
    batch_label: null,
    is_synthetic: true,
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    updated_at: new Date().toISOString(),
    entry_id: id,
    entry_type: "invoice",
    vendor_name: "Northfield Pet Supply Co.",
    invoice_number: "INV-1",
    entry_date: "2026-03-14",
    currency: "USD",
    total_minor: 15200,
    unresolved_checks: [],
    warnings: [],
    ...overrides,
  };
}

const ZERO: DocumentCounts["counts"] = {
  received: 0, read: 0, extracted: 0, needs_review: 0, approved: 0, rejected: 0, exported: 0,
  failed: 0, duplicate: 0,
};  // prettier-ignore

interface World {
  rows: DocumentSummary[];
  counts?: Partial<DocumentCounts["counts"]>;
  batches?: string[];
  next?: string | null;
}

type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response>;

function install(world: World, extra: Handler = () => new Response("no", { status: 404 })) {
  const calls: { url: URL; init?: RequestInit }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    calls.push({ url, init });
    if (url.pathname === "/api/documents/counts") {
      const counts: DocumentCounts["counts"] = { ...ZERO };
      for (const [name, value] of Object.entries(world.counts ?? {})) counts[name] = value ?? 0;
      const body: DocumentCounts = { counts, batches: world.batches ?? [] };
      return Response.json(body);
    }
    if (url.pathname === "/api/documents" && (init?.method ?? "GET") === "GET") {
      const body: DocumentList = { items: world.rows, next_cursor: world.next ?? null };
      return Response.json(body);
    }
    return extra(url, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

function renderInbox() {
  return render(
    <ToastProvider>
      <Inbox />
    </ToastProvider>,
  );
}

beforeEach(() => {
  nextId = 1;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Inbox states", () => {
  it("shows a loading state first, said once to a screen reader", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));
    renderInbox();
    expect(screen.getByText("Loading documents…")).toBeInTheDocument();
  });

  it("shows the empty state with the demo button when nothing has ever been added", async () => {
    install({ rows: [], counts: {} });
    renderInbox();
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load demo documents" })).toBeInTheDocument();
  });

  it("says when a list is empty but other lists are not", async () => {
    install({ rows: [], counts: { approved: 4 } });
    renderInbox();
    expect(await screen.findByText("No needs review documents")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load demo documents" })).toBeNull();
  });

  it("shows an error with the request id and a way to try again", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.startsWith("/api/documents/counts")) return Response.json({ counts: ZERO, batches: [] });
      return Response.json(
        { error: { code: "internal_error", message: "Something went wrong on our side.", request_id: "req-77" } },
        { status: 500 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderInbox();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The list could not be loaded");
    expect(alert).toHaveTextContent("request req-77");
    const asked = () =>
      fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/documents?")).length;
    const before = asked();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(asked()).toBeGreaterThan(before));
  });
});

describe("Inbox rows", () => {
  it("shows file, vendor, date, total, checks, status and age", async () => {
    install({
      rows: [
        row({
          original_filename: "march.pdf",
          unresolved_checks: ["UNKNOWN_VENDOR", "TOTAL_MATCH"],
          warnings: ["SUSPICIOUS_TEXT"],
        }),
      ],
      counts: { needs_review: 1 },
    });
    renderInbox();
    const table = await screen.findByRole("table");
    const body = within(table);
    expect(body.getByRole("link", { name: /march\.pdf/ })).toHaveAttribute("href", "#/review/1");
    expect(body.getByText("Northfield Pet Supply Co.")).toBeInTheDocument();
    expect(body.getByText("14 Mar 2026")).toBeInTheDocument();
    expect(body.getByText("$152.00")).toBeInTheDocument();
    expect(body.getByText("2 blocking")).toBeInTheDocument();
    expect(body.getByText("1 warning")).toBeInTheDocument();
    expect(body.getByText("Needs review")).toBeInTheDocument();
    expect(body.getByText("5 min")).toBeInTheDocument();
    expect(body.getByRole("link", { name: "Review" })).toBeInTheDocument();
  });

  it("says Unknown vendor when no vendor was matched, and shows a credit note as negative", async () => {
    install({
      rows: [row({ vendor_name: null, entry_type: "credit_note" })],
      counts: { needs_review: 1 },
    });
    renderInbox();
    expect(await screen.findByText("Unknown vendor")).toBeInTheDocument();
    expect(screen.getByText("−$152.00")).toBeInTheDocument();
    expect(screen.getByText("Credit")).toBeInTheDocument();
  });

  it("shows all checks passed for a clean document", async () => {
    install({ rows: [row()], counts: { needs_review: 1 } });
    renderInbox();
    expect(await screen.findByText("All checks passed")).toBeInTheDocument();
  });

  it("shows what a processing row is doing in words", async () => {
    install({
      rows: [
        row({ status: "received", vendor_name: null, total_minor: null, entry_id: null, entry_type: null }),
        row({ status: "read", vendor_name: null, total_minor: null, entry_id: null, entry_type: null }),
        row({ status: "extracted", vendor_name: null, total_minor: null, entry_id: null, entry_type: null }),
      ],
    });
    renderInbox();
    expect(await screen.findByText("Reading the pages…")).toBeInTheDocument();
    expect(screen.getByText("Finding the values…")).toBeInTheDocument();
    expect(screen.getByText("Checking the numbers…")).toBeInTheDocument();
    expect(screen.getByText("3 still being read. This list updates by itself.")).toBeInTheDocument();
    expect(screen.queryByText("Unknown vendor")).toBeNull();
  });

  it("admits when a step is slow", async () => {
    install({
      rows: [
        row({
          status: "read",
          updated_at: new Date(Date.now() - 5 * 60_000).toISOString(),
          vendor_name: null,
        }),
      ],
    });
    renderInbox();
    expect(await screen.findByText(/Still working. The model is slow right now./)).toBeInTheDocument();
  });

  it("keeps refreshing while something is processing", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout"] });
    const { calls } = install({ rows: [row({ status: "read", vendor_name: null })] });
    renderInbox();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    const before = calls.filter((c) => c.url.pathname === "/api/documents").length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(calls.filter((c) => c.url.pathname === "/api/documents").length).toBeGreaterThan(before);
  });

  it("renders document text as text, never as markup", async () => {
    const hostile = '<img src=x onerror="alert(1)">.pdf';
    install({
      rows: [row({ original_filename: hostile, vendor_name: "<script>alert(2)</script>" })],
      counts: { needs_review: 1 },
    });
    const { container } = renderInbox();
    expect(await screen.findAllByText(hostile)).not.toHaveLength(0);
    expect(screen.getByText("<script>alert(2)</script>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});

describe("Inbox failed documents", () => {
  it("shows the plain reason and retries from the right stage", async () => {
    const { calls } = install(
      {
        rows: [
          row({
            id: 90,
            status: "failed",
            failure_stage: "extract",
            failure_message: "The model did not give a usable answer. Try again.",
            vendor_name: null,
            total_minor: null,
          }),
        ],
        counts: { failed: 1 },
      },
      () => Response.json({}),
    );
    renderInbox();
    fireEvent.click(await screen.findByRole("button", { name: "Failed 1" }));
    expect(await screen.findByText("The model did not give a usable answer. Try again.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Retry/ }));
    await waitFor(() => {
      const retried = calls.find((c) => c.url.pathname === "/api/documents/90/reprocess");
      expect(retried).toBeDefined();
      expect(JSON.parse(String(retried?.init?.body))).toEqual({ from_stage: "extract" });
    });
    expect(await screen.findByText("Trying again.")).toBeInTheDocument();
  });

  it("offers no retry for a file that was refused at the door", async () => {
    install({
      rows: [row({ status: "failed", failure_stage: "ingest", failure_message: "The file is larger than the 20 MB limit." })],
      counts: { failed: 1 },
    });
    renderInbox();
    fireEvent.click(await screen.findByRole("button", { name: "Failed 1" }));
    expect(await screen.findByText("The file is larger than the 20 MB limit.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
  });
});

describe("Inbox filters", () => {
  it("shows a count on each status chip and starts on Needs review", async () => {
    install({ rows: [row()], counts: { needs_review: 3, approved: 5, failed: 1 } });
    renderInbox();
    const needs = await screen.findByRole("button", { name: "Needs review 3" });
    expect(needs).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Approved 5" })).toHaveAttribute("aria-pressed", "false");
  });

  it("asks for the documents of the chosen chip, including those still being read for Needs review", async () => {
    const { calls } = install({ rows: [row()], counts: { needs_review: 1, approved: 2 } });
    renderInbox();
    await screen.findByRole("table");
    const first = calls.filter((c) => c.url.pathname === "/api/documents").at(-1)!;
    expect(first.url.searchParams.getAll("status")).toEqual(["received", "read", "extracted", "needs_review"]);
    expect(first.url.searchParams.get("order")).toBe("oldest");

    fireEvent.click(screen.getByRole("button", { name: "Approved 2" }));
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === "/api/documents").at(-1)!;
      expect(last.url.searchParams.getAll("status")).toEqual(["approved"]);
    });
  });

  it("searches after a short pause and by the chosen problem and batch", async () => {
    const { calls } = install({ rows: [row()], counts: { needs_review: 1 }, batches: ["Upload 2026-03-14 10:00"] });
    renderInbox();
    await screen.findByRole("table");
    fireEvent.change(screen.getByPlaceholderText("Vendor, invoice number or file"), { target: { value: "north" } });
    fireEvent.change(screen.getByLabelText("Problem"), { target: { value: "UNKNOWN_VENDOR" } });
    fireEvent.change(screen.getByLabelText("Batch"), { target: { value: "Upload 2026-03-14 10:00" } });
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === "/api/documents").at(-1)!;
      expect(last.url.searchParams.get("q")).toBe("north");
      expect(last.url.searchParams.get("check")).toBe("UNKNOWN_VENDOR");
      expect(last.url.searchParams.get("batch")).toBe("Upload 2026-03-14 10:00");
    });
  });

  it("keeps what was typed out of the address bar", async () => {
    install({ rows: [row()], counts: { needs_review: 1 } });
    renderInbox();
    await screen.findByRole("table");
    fireEvent.change(screen.getByPlaceholderText("Vendor, invoice number or file"), { target: { value: "secret vendor" } });
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(window.location.href).not.toContain("secret");
    expect(window.location.hash).not.toContain("secret");
  });

  it("offers to clear filters when they hide everything", async () => {
    install({ rows: [], counts: { needs_review: 2 } });
    renderInbox();
    await screen.findByText("No needs review documents");
    fireEvent.change(screen.getByLabelText("Problem"), { target: { value: "LINE_MATH" } });
    expect(await screen.findByText("Nothing matches those filters")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear the filters" }));
    expect(await screen.findByText("No needs review documents")).toBeInTheDocument();
    expect(screen.getByLabelText("Problem")).toHaveValue("");
  });

  it("can put blocking checks first, and newest first", async () => {
    const { calls } = install({
      rows: [
        row({ original_filename: "clean.pdf" }),
        row({ original_filename: "worst.pdf", unresolved_checks: ["TOTAL_MATCH", "LINE_MATH"] }),
        row({ original_filename: "one.pdf", unresolved_checks: ["UNKNOWN_VENDOR"] }),
      ],
      counts: { needs_review: 3 },
    });
    renderInbox();
    await screen.findByRole("table");
    fireEvent.change(screen.getByLabelText("Order"), { target: { value: "blocking" } });
    const names = () => screen.getAllByRole("link", { name: /\.pdf/ }).map((a) => a.textContent);
    await waitFor(() => expect(names()).toEqual(["worst.pdf", "one.pdf", "clean.pdf"]));
    fireEvent.change(screen.getByLabelText("Order"), { target: { value: "newest" } });
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === "/api/documents").at(-1)!;
      expect(last.url.searchParams.get("order")).toBe("newest");
    });
  });

  it("shows more when the list continues", async () => {
    const { calls } = install({ rows: [row()], counts: { needs_review: 80 }, next: "1" });
    renderInbox();
    fireEvent.click(await screen.findByRole("button", { name: "Show more" }));
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === "/api/documents").at(-1)!;
      expect(last.url.searchParams.get("cursor")).toBe("1");
    });
  });
});

describe("Inbox upload", () => {
  function pick(files: File[]) {
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files } });
  }

  it("sends the files with a batch label, tells you, and lists what was not added", async () => {
    const response: UploadResponse = {
      results: [
        { filename: "a.pdf", outcome: "accepted", document_id: 1, status: "received", message: null },
        { filename: "notes.txt", outcome: "rejected", document_id: null, status: null, message: "This file is not a PDF, PNG or JPEG, so it cannot be read." },
        { filename: "again.pdf", outcome: "duplicate", document_id: 2, status: "duplicate", message: null },
      ],
    };
    const { calls } = install({ rows: [], counts: {} }, (url) =>
      url.pathname === "/api/documents" ? Response.json(response) : new Response("no", { status: 404 }),
    );
    renderInbox();
    await screen.findByText("Nothing here yet");
    pick([new File(["x"], "a.pdf"), new File(["y"], "notes.txt")]);
    expect(await screen.findByText("1 document added. Reading it now.")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Files that were not added" });
    expect(within(list).getByText(/notes\.txt: This file is not a PDF/)).toBeInTheDocument();
    expect(within(list).getByText("again.pdf: Already in the list.")).toBeInTheDocument();
    const post = calls.find((c) => c.init?.method === "POST")!;
    expect((post.init!.body as FormData).get("batch_label")).toMatch(/^Upload \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });

  it("shows the API's message and request id when the upload itself fails", async () => {
    install({ rows: [], counts: {} }, () =>
      Response.json(
        { error: { code: "too_many_files", message: "Upload at most 50 files at a time.", request_id: "req-9" } },
        { status: 413 },
      ),
    );
    renderInbox();
    await screen.findByText("Nothing here yet");
    pick([new File(["x"], "a.pdf")]);
    const alert = await screen.findByText(/Upload at most 50 files at a time/);
    expect(alert).toHaveTextContent("request req-9");
  });

  it("loads the demo documents from the empty state", async () => {
    const response: UploadResponse = {
      results: [
        { filename: "inv-0001.pdf", outcome: "accepted", document_id: 1, status: "received", message: null },
        { filename: "inv-0002.pdf", outcome: "accepted", document_id: 2, status: "received", message: null },
      ],
    };
    const { calls } = install({ rows: [], counts: {} }, (url) =>
      url.pathname === "/api/demo/load" ? Response.json(response) : new Response("no", { status: 404 }),
    );
    renderInbox();
    fireEvent.click(await screen.findByRole("button", { name: "Load demo documents" }));
    expect(await screen.findByText("2 documents added. Reading them now.")).toBeInTheDocument();
    expect(calls.some((c) => c.url.pathname === "/api/demo/load")).toBe(true);
  });

  it("explains when the demo documents have not been made", async () => {
    install({ rows: [], counts: {} }, () =>
      Response.json(
        { error: { code: "demo_missing", message: "The demo documents have not been made yet. Run: python -m tools.synthetic.demo", request_id: "r" } },
        { status: 404 },
      ),
    );
    renderInbox();
    fireEvent.click(await screen.findByRole("button", { name: "Load demo documents" }));
    expect(await screen.findByText(/python -m tools\.synthetic\.demo/)).toBeInTheDocument();
  });

  it("accepts a drop", async () => {
    const response: UploadResponse = {
      results: [{ filename: "a.pdf", outcome: "accepted", document_id: 1, status: "received", message: null }],
    };
    const { calls } = install({ rows: [], counts: {} }, () => Response.json(response));
    renderInbox();
    await screen.findByText("Nothing here yet");
    const zone = screen.getByRole("heading", { name: "Add invoices and receipts" }).closest("section")!;
    fireEvent.dragOver(zone);
    expect(zone.className).toContain("upload-over");
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["x"], "a.pdf")] } });
    await waitFor(() => expect(calls.some((c) => c.init?.method === "POST")).toBe(true));
  });
});
