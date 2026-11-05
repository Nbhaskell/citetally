import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CheckOut, DocumentDetail, DocumentSummary } from "../api/client";
import {
  checkFixture,
  checksFixture,
  detailFixture,
  entryFixture,
  evidenceRow,
} from "../review/fixtures";
import { ToastProvider } from "../ui/Toast";
import Review from "./Review";

interface Call {
  method: string;
  path: string;
  search: URLSearchParams;
  body: unknown;
}

function summary(id: number, overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    id,
    original_filename: `doc-${id}.pdf`,
    mime_type: "application/pdf",
    source_kind: "digital_pdf",
    page_count: 1,
    size_bytes: 1,
    status: "needs_review",
    duplicate_of: null,
    failure_stage: null,
    failure_message: null,
    batch_label: null,
    is_synthetic: true,
    created_at: "2026-03-14T10:00:00.000Z",
    updated_at: "2026-03-14T10:00:00.000Z",
    entry_id: id,
    entry_type: "invoice",
    vendor_name: "Other Vendor",
    invoice_number: `INV-${id}`,
    entry_date: "2026-03-10",
    currency: "USD",
    total_minor: 9900,
    unresolved_checks: [],
    warnings: [],
    ...overrides,
  };
}

type Responder = (call: Call) => Response | undefined | Promise<Response | undefined>;

function install(
  detail: DocumentDetail,
  options: { queue?: number[]; responders?: Responder[]; vendors?: unknown[]; suggestions?: unknown[] } = {},
) {
  const calls: Call[] = [];
  let current = detail;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const call: Call = {
      method: init?.method ?? "GET",
      path: url.pathname,
      search: url.searchParams,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    };
    calls.push(call);
    for (const responder of options.responders ?? []) {
      const response = await responder(call);
      if (response) return response;
    }
    if (call.path === `/api/documents/${detail.document.id}` && call.method === "GET") return Response.json(current);
    if (call.path === "/api/categories") {
      return Response.json([
        { code: "SUPPLIES", name: "Supplies", is_active: true },
        { code: "FOOD", name: "Food and drinks", is_active: true },
      ]);
    }
    if (call.path === "/api/documents" && call.method === "GET") {
      const ids = options.queue ?? [detail.document.id];
      const q = call.search.get("q");
      if (q) return Response.json({ items: [summary(40, { vendor_name: "Northfield" })], next_cursor: null });
      return Response.json({ items: ids.map((n) => summary(n)), next_cursor: null });
    }
    if (call.path === "/api/vendors") return Response.json(options.vendors ?? []);
    if (call.path.endsWith("/vendor-suggestions")) return Response.json(options.suggestions ?? []);
    return new Response(JSON.stringify({ error: { code: "not_found", message: "no route in the test", request_id: "t" } }), { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    calls,
    set: (next: DocumentDetail) => {
      current = next;
    },
    sent: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path),
  };
}

function renderReview(id = 5) {
  return render(
    <ToastProvider>
      <Review id={id} />
    </ToastProvider>,
  );
}

const failing = (code: Parameters<typeof checkFixture>[0], detail: Record<string, unknown>): CheckOut =>
  checkFixture(code, detail, { passed: false });

const unknownVendor = () => checksFixture({ UNKNOWN_VENDOR: failing("UNKNOWN_VENDOR", {}) });

beforeEach(() => {
  window.location.hash = "#/review/5";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("states", () => {
  it("shows a loading state", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));
    renderReview();
    expect(screen.getByText("Loading the document…")).toBeInTheDocument();
  });

  it("says when the document does not exist", async () => {
    install(detailFixture(), {
      responders: [() => Response.json({ error: { code: "not_found", message: "Document 5 was not found.", request_id: "r1" } }, { status: 404 })],
    });
    renderReview();
    expect(await screen.findByText("That document does not exist")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the Inbox" })).toBeInTheDocument();
  });

  it("shows an error with the request id and tries again", async () => {
    let failOnce = true;
    install(detailFixture(), {
      responders: [
        (c) => {
          if (c.path === "/api/documents/5" && failOnce) {
            failOnce = false;
            return Response.json({ error: { code: "internal_error", message: "Something went wrong on our side.", request_id: "req-5" } }, { status: 500 });
          }
        },
      ],
    });
    renderReview();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("could not be loaded");
    expect(alert).toHaveTextContent("request req-5");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("brightway-march.pdf");
  });

  it("shows what a document that is still being read is doing", async () => {
    install(detailFixture({ entry: null, evidence: [], checks: [], pages: [], document: { ...detailFixture().document, status: "read" } }));
    renderReview();
    expect(await screen.findByText("Finding the values…")).toBeInTheDocument();
    expect(screen.getByText(/updates by itself/)).toBeInTheDocument();
  });

  it("shows the plain reason a document failed and offers to reprocess it", async () => {
    install(
      detailFixture({
        entry: null,
        evidence: [],
        checks: [],
        document: { ...detailFixture().document, status: "failed", failure_stage: "extract", failure_message: "The model did not give a usable answer. Try again." },
      }),
    );
    renderReview();
    expect(await screen.findByText("This document could not be read")).toBeInTheDocument();
    expect(screen.getByText("The model did not give a usable answer. Try again.")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Reprocess…" })[0]);
    expect(screen.getByRole("dialog", { name: "Reprocess this document" })).toBeInTheDocument();
  });

  it("links a duplicate to the document it repeats", async () => {
    install(detailFixture({ entry: null, evidence: [], checks: [], document: { ...detailFixture().document, status: "duplicate", duplicate_of: 2 } }));
    renderReview();
    expect(await screen.findByRole("link", { name: "document 2" })).toHaveAttribute("href", "#/review/2");
  });
});

describe("the page and the values", () => {
  it("draws a box for each value found, in fractions of the page, and lists every value", async () => {
    install(
      detailFixture({
        evidence: [
          evidenceRow("total", "$236.50", [0.6, 0.8, 0.8, 0.83]),
          evidenceRow("invoice_number", "INV-2042", null),
        ],
      }),
    );
    const { container } = renderReview();
    await screen.findByRole("heading", { level: 1 });
    const boxes = container.querySelectorAll<HTMLElement>(".box");
    expect(boxes).toHaveLength(1);
    expect(boxes[0].style.left).toBe("60%");
    expect(boxes[0].style.top).toBe("80%");
    const list = screen.getByRole("list", { name: "Where each value was found" });
    expect(within(list).getByText("found on page 1")).toBeInTheDocument();
    expect(within(list).getByText("not found on the page")).toBeInTheDocument();
    expect(screen.getByAltText("Page 1 of the document")).toHaveAttribute("src", "/api/documents/5/pages/1/image");
  });

  it("hides the boxes on request, still outlines the value being pointed at, and shows them again", async () => {
    window.localStorage.removeItem("citetally.page-boxes");
    install(
      detailFixture({
        evidence: [
          evidenceRow("total", "$236.50", [0.6, 0.8, 0.8, 0.83]),
          evidenceRow("invoice_number", "INV-2042", [0.1, 0.1, 0.3, 0.13]),
        ],
      }),
    );
    const { container } = renderReview();
    await screen.findByRole("heading", { level: 1 });
    expect(container.querySelectorAll(".box")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Hide boxes" }));
    expect(container.querySelectorAll(".box")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Show boxes" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: /Total\s*found on page 1/ }));
    await waitFor(() => expect(container.querySelectorAll(".box")).toHaveLength(1));
    expect(container.querySelector(".box")?.getAttribute("data-key")).toBe("total");
    fireEvent.click(screen.getByRole("button", { name: "Show boxes" }));
    expect(container.querySelectorAll(".box")).toHaveLength(2);
    window.localStorage.removeItem("citetally.page-boxes");
  });

  it("remembers that the boxes were hidden", async () => {
    window.localStorage.setItem("citetally.page-boxes", "hidden");
    install(detailFixture({ evidence: [evidenceRow("total", "$236.50", [0.6, 0.8, 0.8, 0.83])] }));
    const { container } = renderReview();
    await screen.findByRole("heading", { level: 1 });
    expect(container.querySelectorAll(".box")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Show boxes" })).toBeInTheDocument();
    window.localStorage.removeItem("citetally.page-boxes");
  });

  it("offers the page text as read, as plain text", async () => {
    install(detailFixture());
    renderReview();
    await screen.findByRole("heading", { level: 1 });
    const text = screen.getByText(/Brightway Supply\s+Invoice INV-2042/);
    expect(text.tagName).toBe("PRE");
  });

  it("clicking a value in the list moves to its field, and focusing a field marks its box", async () => {
    install(detailFixture());
    const { container } = renderReview();
    await screen.findByRole("heading", { level: 1 });
    fireEvent.click(screen.getByRole("button", { name: /Total\s*found on page 1/ }));
    await waitFor(() => expect(screen.getByLabelText("Total")).toHaveFocus());
    expect(container.querySelector(".box-active")).not.toBeNull();
    expect(container.querySelector(".box-active")?.getAttribute("data-key")).toBe("total");
  });

  it("says in the form when a value was not on the page", async () => {
    install(detailFixture({ evidence: [evidenceRow("invoice_number", "INV-2042", null)] }));
    renderReview();
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getAllByText("Not found on the page").length).toBeGreaterThan(0);
  });

  it("shows several pages one at a time", async () => {
    const base = detailFixture();
    install(
      detailFixture({
        pages: [base.pages[0], { ...base.pages[0], page_number: 2, image_url: "/api/documents/5/pages/2/image", text: "second" }],
      }),
    );
    renderReview();
    await screen.findByText("Page 1 of 2");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByAltText("Page 2 of the document")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("renders document text as text, never as markup", async () => {
    install(
      detailFixture({
        entry: entryFixture({ vendor_name_raw: "<img src=x onerror=alert(1)>", invoice_number: "<script>1</script>" }),
        checks: unknownVendor(),
      }),
    );
    const { container } = renderReview();
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getAllByText(/<img src=x onerror=alert\(1\)>/).length).toBeGreaterThan(0);
    expect(container.querySelector("img[src='x']")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});

describe("the checks", () => {
  it("groups problems, explains them with numbers, and folds the passed checks away", async () => {
    install(
      detailFixture({
        checks: checksFixture({
          TOTAL_MATCH: failing("TOTAL_MATCH", { expected: 23550, stated: 23650 }),
          UNKNOWN_VENDOR: failing("UNKNOWN_VENDOR", {}),
          CURRENCY_CHECK: checkFixture("CURRENCY_CHECK", { stated: "EUR", usual: "USD" }, { passed: false }),
        }),
      }),
    );
    renderReview();
    await screen.findByText("Must be resolved before approving");
    expect(screen.getByText("Subtotal + tax + shipping − discount is $235.50. The page says $236.50.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Worth a look" })).toBeInTheDocument();
    expect(screen.getByText("This invoice is in EUR. Your usual is USD.")).toBeInTheDocument();
    expect(screen.getByText("11 checks passed")).toBeInTheDocument();
    expect(screen.getAllByText("Must be resolved")).toHaveLength(2);
  });

  it("says when nothing needs attention", async () => {
    install(detailFixture());
    renderReview();
    expect(await screen.findByText("Nothing needs attention.")).toBeInTheDocument();
    expect(screen.getByText("14 checks passed")).toBeInTheDocument();
  });

  it("'Go to the value' goes to the field and 'Show on page' highlights its box", async () => {
    install(
      detailFixture({ checks: checksFixture({ TOTAL_MATCH: failing("TOTAL_MATCH", { expected: 23550, stated: 23650 }) }) }),
    );
    const { container } = renderReview();
    await screen.findByText("Must be resolved before approving");
    const checks = within(screen.getByRole("region", { name: "Checks" }));
    fireEvent.click(checks.getByRole("button", { name: "Show on page" }));
    expect(container.querySelector(".box-active")?.getAttribute("data-key")).toBe("total");
    fireEvent.click(checks.getByRole("button", { name: "Go to the value" }));
    await waitFor(() => expect(screen.getByLabelText("Total")).toHaveFocus());
  });

  it("tells you to keep printed figures as printed when the page's own arithmetic is off", async () => {
    install(detailFixture({ checks: checksFixture({ TOTAL_MATCH: failing("TOTAL_MATCH", { expected: 23550, stated: 23650 }) }) }));
    renderReview();
    await screen.findByText("Must be resolved before approving");
    const checks = within(screen.getByRole("region", { name: "Checks" }));
    expect(checks.getByText(/Keep the figures as the page prints them/)).toBeInTheDocument();
    expect(checks.queryByRole("button", { name: "Fix value" })).toBeNull();
  });

  it("keeps 'Fix value' for a check that is about a missing or misread value", async () => {
    install(detailFixture({ checks: checksFixture({ REQUIRED_FIELDS: failing("REQUIRED_FIELDS", { missing: ["invoice_number"] }) }) }));
    renderReview();
    await screen.findByText("Must be resolved before approving");
    const checks = within(screen.getByRole("region", { name: "Checks" }));
    expect(checks.getByRole("button", { name: "Fix value" })).toBeInTheDocument();
    expect(checks.queryByText(/Keep the figures as the page prints them/)).toBeNull();
  });
});

describe("approving", () => {
  it("is off while a blocking check is unresolved, and says how many", async () => {
    install(detailFixture({ checks: unknownVendor() }));
    renderReview();
    const approve = await screen.findByRole("button", { name: "Approve entry" });
    expect(approve).toBeDisabled();
    expect(screen.getByText("1 check must be resolved first")).toBeInTheDocument();
    expect(approve).toHaveAccessibleDescription("1 check must be resolved first");
  });

  it("is on when everything passes, and sends the time spent", async () => {
    const fake = install(detailFixture(), {
      queue: [5, 6],
      responders: [(c) => (c.path === "/api/documents/5/approve" ? Response.json({ document: detailFixture().document, review: {} }) : undefined)],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
    await waitFor(() => expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(1));
    const body = fake.sent("POST", "/api/documents/5/approve")[0].body as { overrides: unknown[]; review_seconds: number };
    expect(body.overrides).toEqual([]);
    expect(body.review_seconds).toBeGreaterThanOrEqual(0);
    expect(await screen.findByText("Approved INV-2042.")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/review/6");
  });

  it("opens the Inbox when it was the last one waiting", async () => {
    install(detailFixture(), {
      queue: [5],
      responders: [(c) => (c.path === "/api/documents/5/approve" ? Response.json({ document: detailFixture().document, review: {} }) : undefined)],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
    expect(await screen.findByText("That was the last one waiting.")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/");
  });

  it("offers Undo, which reopens the document and goes back to it", async () => {
    const fake = install(detailFixture(), {
      queue: [5, 6],
      responders: [
        (c) => (c.path === "/api/documents/5/approve" ? Response.json({ document: detailFixture().document, review: {} }) : undefined),
        (c) => (c.path === "/api/documents/5/reopen" ? Response.json({ document: detailFixture().document, review: {} }) : undefined),
      ],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(fake.sent("POST", "/api/documents/5/reopen")).toHaveLength(1));
    await waitFor(() => expect(window.location.hash).toBe("#/review/5"));
  });

  it("accepts a failed blocking check only with a written reason, and sends it with the approval", async () => {
    const fake = install(detailFixture({ checks: unknownVendor() }), {
      queue: [5],
      responders: [(c) => (c.path === "/api/documents/5/approve" ? Response.json({ document: detailFixture().document, review: {} }) : undefined)],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Override with reason" }));
    const dialog = screen.getByRole("dialog", { name: "New vendor" });
    const accept = within(dialog).getByRole("button", { name: "Accept this check" });
    expect(accept).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("I've checked this and it's correct because…"), {
      target: { value: "A new supplier; I will add them after lunch." },
    });
    fireEvent.click(accept);
    expect(await screen.findByText(/Will be accepted when you approve, because:/)).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: "Approve entry" });
    expect(approve).toBeEnabled();
    fireEvent.click(approve);
    await waitFor(() => expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(1));
    expect((fake.sent("POST", "/api/documents/5/approve")[0].body as { overrides: unknown }).overrides).toEqual([
      { check_code: "UNKNOWN_VENDOR", reason: "A new supplier; I will add them after lunch." },
    ]);
  });

  it("lets you take an override back", async () => {
    install(detailFixture({ checks: unknownVendor() }));
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Override with reason" }));
    fireEvent.change(screen.getByLabelText("I've checked this and it's correct because…"), {
      target: { value: "Looks right to me, honestly." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Accept this check" }));
    fireEvent.click(await screen.findByRole("button", { name: "Take back" }));
    expect(screen.getByRole("button", { name: "Approve entry" })).toBeDisabled();
  });

  describe("checked against the picture", () => {
    const notFound = [
      { field: "total", line: null, printed: "$236.50" },
      { field: "amount", line: 1, printed: "$54.00" },
    ];
    const pictureRead = (mode = "text_and_image", method = "ocr"): DocumentDetail => {
      const base = detailFixture({ checks: checksFixture({ VALUE_IN_DOCUMENT: failing("VALUE_IN_DOCUMENT", { checked: 4, not_found: notFound }) }) });
      return {
        ...base,
        pages: base.pages.map((page) => ({ ...page, read_method: method })),
        extraction: {
          id: 1, attempt: 1, provider: "ollama", model: "qwen3-vl:8b-instruct", extract_mode: mode,
          prompt_version: "v1", input_tokens: null, output_tokens: null, duration_ms: 1000, created_at: "x",
        },
      } as DocumentDetail;
    };

    it("records one confirmation for every unlocated value, and only after each one is marked as matching", async () => {
      const fake = install(pictureRead(), {
        queue: [5],
        responders: [(c) => (c.path === "/api/documents/5/approve" ? Response.json({ document: detailFixture().document, review: {} }) : undefined)],
      });
      renderReview();
      fireEvent.click(await screen.findByRole("button", { name: "Checked against the picture" }));
      const dialog = screen.getByRole("dialog", { name: "Check against the picture" });
      expect(within(dialog).getByText(/\$236\.50/)).toBeInTheDocument();
      expect(within(dialog).getByText(/\$54\.00/)).toBeInTheDocument();
      const confirm = within(dialog).getByRole("button", { name: "Confirm checked against the picture" });
      expect(confirm).toBeDisabled();
      const matches = within(dialog).getAllByRole("radio", { name: "Matches the picture" });
      expect(matches).toHaveLength(2);
      fireEvent.click(matches[0]);
      expect(confirm).toBeDisabled(); // one value is still undecided
      fireEvent.click(matches[1]);
      expect(confirm).toBeEnabled();
      fireEvent.click(confirm);
      expect(await screen.findByText(/Will be accepted when you approve, because:/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Approve entry" }));
      await waitFor(() => expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(1));
      const sent = (fake.sent("POST", "/api/documents/5/approve")[0].body as { overrides: { check_code: string; reason: string }[] }).overrides;
      expect(sent).toEqual([{ check_code: "VALUE_IN_DOCUMENT", reason: "Checked against the picture: 2 values the page words did not place." }]);
      expect(JSON.stringify(sent)).not.toContain("236");
    });

    it("cannot be confirmed while any value is marked as not what the picture shows", async () => {
      install(pictureRead());
      renderReview();
      fireEvent.click(await screen.findByRole("button", { name: "Checked against the picture" }));
      const dialog = screen.getByRole("dialog", { name: "Check against the picture" });
      for (const radio of within(dialog).getAllByRole("radio", { name: "Matches the picture" })) fireEvent.click(radio);
      fireEvent.click(within(dialog).getAllByRole("radio", { name: "Not what the picture shows" })[1]);
      expect(within(dialog).getByRole("button", { name: "Confirm checked against the picture" })).toBeDisabled();
      expect(within(dialog).getByText(/Close this and correct or clear it in the form/)).toBeInTheDocument();
    });

    it("is not offered when the text reading, not a picture, produced the values", async () => {
      install(pictureRead("text_only"));
      renderReview();
      await screen.findByRole("button", { name: "Override with reason" });
      expect(screen.queryByRole("button", { name: "Checked against the picture" })).toBeNull();
    });

    it("is not offered for a page that has a text layer", async () => {
      install(pictureRead("text_and_image", "text_layer"));
      renderReview();
      await screen.findByRole("button", { name: "Override with reason" });
      expect(screen.queryByRole("button", { name: "Checked against the picture" })).toBeNull();
    });

    it("is not offered for any other check", async () => {
      const detail = pictureRead();
      install({ ...detail, checks: unknownVendor() });
      renderReview();
      await screen.findByRole("button", { name: "Override with reason" });
      expect(screen.queryByRole("button", { name: "Checked against the picture" })).toBeNull();
    });
  });

  describe("lines with no quantity", () => {
    const noQuantity = () =>
      detailFixture({
        entry: entryFixture({
          lines: [
            { ...entryFixture().lines[0], quantity: null },
            { ...entryFixture().lines[0], id: 12, line_number: 4, description: "Elbow", quantity: "2" },
          ],
        }),
      });
    const approveResponder: Responder = (c) =>
      c.path === "/api/documents/5/approve" ? Response.json({ document: detailFixture().document, review: {} }) : undefined;

    it("asks about them before approving, naming the lines, and sends nothing until confirmed", async () => {
      const fake = install(noQuantity(), { queue: [5], responders: [approveResponder] });
      renderReview();
      fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
      const dialog = screen.getByRole("dialog", { name: "Lines with no quantity" });
      expect(within(dialog).getByText(/Line 3/)).toBeInTheDocument();
      expect(within(dialog).queryByText(/Line 4/)).toBeNull();
      expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(0);
      const go = within(dialog).getByRole("button", { name: "Approve anyway" });
      expect(go).toBeDisabled();
      fireEvent.click(within(dialog).getByRole("checkbox"));
      fireEvent.click(go);
      await waitFor(() => expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(1));
    });

    it("lets you go back to fill them in without approving", async () => {
      const fake = install(noQuantity(), { queue: [5], responders: [approveResponder] });
      renderReview();
      fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
      fireEvent.click(within(screen.getByRole("dialog", { name: "Lines with no quantity" })).getByRole("button", { name: "Go back" }));
      expect(screen.queryByRole("dialog", { name: "Lines with no quantity" })).toBeNull();
      expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(0);
    });

    it("does not ask when every line has a quantity", async () => {
      const fake = install(detailFixture(), { queue: [5], responders: [approveResponder] });
      renderReview();
      fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
      await waitFor(() => expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(1));
      expect(screen.queryByRole("dialog", { name: "Lines with no quantity" })).toBeNull();
    });

    it("leaves a flat fee, with no quantity and no price, alone", async () => {
      const fee = { ...entryFixture().lines[0], quantity: null, unit_price: null, description: "Fee" };
      const fake = install(detailFixture({ entry: entryFixture({ lines: [fee] }) }), { queue: [5], responders: [approveResponder] });
      renderReview();
      fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
      await waitFor(() => expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(1));
      expect(screen.queryByText(/No quantity read/)).toBeNull();
    });

    const noNumbers = () =>
      detailFixture({
        entry: entryFixture({
          lines: [
            { ...entryFixture().lines[0], quantity: null, unit_price: null, amount_minor: null, description: "Film cassette" },
            { ...entryFixture().lines[0], id: 12, line_number: 4, description: "Elbow", quantity: "2" },
          ],
        }),
      });

    it("marks a line that has only a description as having no numbers read", async () => {
      install(noNumbers());
      renderReview();
      expect(await screen.findByText(/No numbers read for this line/)).toBeInTheDocument();
    });

    it("asks about lines with no numbers before approving, naming them", async () => {
      const fake = install(noNumbers(), { queue: [5], responders: [approveResponder] });
      renderReview();
      fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
      const dialog = screen.getByRole("dialog", { name: "Lines with missing numbers" });
      expect(within(dialog).getByText(/Line 3/)).toBeInTheDocument();
      expect(within(dialog).queryByText(/Line 4/)).toBeNull();
      expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(0);
      const go = within(dialog).getByRole("button", { name: "Approve anyway" });
      expect(go).toBeDisabled();
      fireEvent.click(within(dialog).getByRole("checkbox"));
      fireEvent.click(go);
      await waitFor(() => expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(1));
    });

    it("does not treat a flat fee that prints an amount as having no numbers", async () => {
      const fee = { ...entryFixture().lines[0], quantity: null, unit_price: null, description: "Fee" };
      const fake = install(detailFixture({ entry: entryFixture({ lines: [fee] }) }), { queue: [5], responders: [approveResponder] });
      renderReview();
      fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
      await waitFor(() => expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(1));
      expect(screen.queryByText(/No numbers read/)).toBeNull();
    });

    it("marks the line in the form as having no quantity read", async () => {
      install(noQuantity());
      renderReview();
      expect(await screen.findByText(/No quantity read/)).toBeInTheDocument();
    });
  });

  it("shows the API's reason and refreshes when approval is refused", async () => {
    const fake = install(detailFixture(), {
      responders: [
        (c) =>
          c.path === "/api/documents/5/approve"
            ? Response.json({ error: { code: "approval_blocked", message: "Blocking checks are not resolved: TOTAL_MATCH", request_id: "r9" } }, { status: 409 })
            : undefined,
      ],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Approve entry" }));
    expect(await screen.findByText(/Blocking checks are not resolved: TOTAL_MATCH \(request r9\)/)).toBeInTheDocument();
    await waitFor(() => expect(fake.sent("GET", "/api/documents/5").length).toBeGreaterThan(1));
  });
});

describe("editing", () => {
  it("saves a text value when you leave the box, and says so", async () => {
    const updated = detailFixture({ entry: entryFixture({ invoice_number: "INV-9" }) });
    const fake = install(detailFixture(), {
      responders: [(c) => (c.method === "PATCH" ? Response.json(updated) : undefined)],
    });
    renderReview();
    const box = await screen.findByLabelText("Invoice number");
    fireEvent.change(box, { target: { value: "INV-9" } });
    fireEvent.blur(box);
    await waitFor(() => expect(fake.sent("PATCH", "/api/entries/1")).toHaveLength(1));
    expect(fake.sent("PATCH", "/api/entries/1")[0].body).toEqual({ invoice_number: "INV-9" });
    expect(await screen.findByText("Saved. Nothing is left to resolve.")).toBeInTheDocument();
  });

  it("saves nothing when nothing changed", async () => {
    const fake = install(detailFixture());
    renderReview();
    const box = await screen.findByLabelText("Invoice number");
    fireEvent.focus(box);
    fireEvent.blur(box);
    expect(fake.sent("PATCH", "/api/entries/1")).toHaveLength(0);
  });

  it("turns an amount into minor units and tells you how many checks are left", async () => {
    const after = detailFixture({ checks: checksFixture({ TOTAL_MATCH: failing("TOTAL_MATCH", { expected: 23650, stated: 80000 }) }) });
    const fake = install(detailFixture(), { responders: [(c) => (c.method === "PATCH" ? Response.json(after) : undefined)] });
    renderReview();
    const box = await screen.findByLabelText("Total");
    fireEvent.change(box, { target: { value: "$800.00" } });
    fireEvent.blur(box);
    await waitFor(() => expect(fake.sent("PATCH", "/api/entries/1")).toHaveLength(1));
    expect(fake.sent("PATCH", "/api/entries/1")[0].body).toEqual({ total_minor: 80000 });
    expect(await screen.findByText("Saved. 1 check must be resolved.")).toBeInTheDocument();
    expect(screen.getByText("Total doesn't add up")).toBeInTheDocument();
  });

  it("refuses an amount that is not clearly an amount, and sends nothing", async () => {
    const fake = install(detailFixture());
    renderReview();
    const box = await screen.findByLabelText("Total");
    fireEvent.change(box, { target: { value: "12.345" } });
    fireEvent.blur(box);
    expect(await screen.findByText("Enter an amount like 152.00.")).toBeInTheDocument();
    expect(box).toHaveAttribute("aria-invalid", "true");
    expect(fake.sent("PATCH", "/api/entries/1")).toHaveLength(0);
  });

  it("refuses a currency that is not three letters", async () => {
    const fake = install(detailFixture());
    renderReview();
    const box = await screen.findByLabelText("Currency");
    fireEvent.change(box, { target: { value: "dollars" } });
    fireEvent.blur(box);
    expect(await screen.findByText("Use a three-letter code like USD.")).toBeInTheDocument();
    expect(fake.sent("PATCH", "/api/entries/1")).toHaveLength(0);
  });

  it("puts a value back and shows the reason when saving fails", async () => {
    install(detailFixture(), {
      responders: [
        (c) =>
          c.method === "PATCH"
            ? Response.json({ error: { code: "not_editable", message: "Only a document waiting for review can be edited.", request_id: "r7" } }, { status: 409 })
            : undefined,
      ],
    });
    renderReview();
    const box = await screen.findByLabelText("Invoice number");
    fireEvent.change(box, { target: { value: "INV-9" } });
    fireEvent.blur(box);
    expect(await screen.findByText(/Not saved: Only a document waiting for review can be edited. \(request r7\)/)).toBeInTheDocument();
    expect(box).toHaveValue("INV-2042");
  });

  it("sends the whole list of lines, changing only the one edited", async () => {
    const entry = entryFixture({
      lines: [
        { id: 11, entry_id: 1, line_number: 1, description: "Pipe", quantity: "10", unit_price: "4.50", amount_minor: 4500, tax_rate: null, created_at: "x" },
        { id: 12, entry_id: 1, line_number: 2, description: "Elbow", quantity: "2", unit_price: "3.00", amount_minor: 600, tax_rate: null, created_at: "x" },
      ],
    });
    const fake = install(detailFixture({ entry }), { responders: [(c) => (c.method === "PATCH" ? Response.json(detailFixture({ entry })) : undefined)] });
    renderReview();
    const box = await screen.findByLabelText("Amount, line 2");
    fireEvent.change(box, { target: { value: "7.00" } });
    fireEvent.blur(box);
    await waitFor(() => expect(fake.sent("PATCH", "/api/entries/1")).toHaveLength(1));
    expect(fake.sent("PATCH", "/api/entries/1")[0].body).toEqual({ lines: [{ id: 11 }, { id: 12, amount_minor: 700 }] });
  });

  it("adds and removes lines", async () => {
    const fake = install(detailFixture(), { responders: [(c) => (c.method === "PATCH" ? Response.json(detailFixture()) : undefined)] });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Add a line" }));
    await waitFor(() => expect(fake.sent("PATCH", "/api/entries/1")).toHaveLength(1));
    expect(fake.sent("PATCH", "/api/entries/1")[0].body).toEqual({ lines: [{ id: 11 }, {}] });
    fireEvent.click(screen.getByRole("button", { name: "Remove line 3" }));
    await waitFor(() => expect(fake.sent("PATCH", "/api/entries/1")).toHaveLength(2));
    expect(fake.sent("PATCH", "/api/entries/1")[1].body).toEqual({ lines: [] });
  });

  it("shows each line's arithmetic in words, and the numbers when it does not match", async () => {
    install(
      detailFixture({
        checks: checksFixture({ LINE_MATH: failing("LINE_MATH", { mismatches: [{ line: 3, expected: 4500, stated: 5400 }] }) }),
        entry: entryFixture({
          lines: [
            { id: 11, entry_id: 1, line_number: 3, description: "Pipe", quantity: "10", unit_price: "4.50", amount_minor: 5400, tax_rate: null, created_at: "x" },
            { id: 12, entry_id: 1, line_number: 4, description: "Elbow", quantity: "2", unit_price: "3.00", amount_minor: 600, tax_rate: null, created_at: "x" },
            { id: 13, entry_id: 1, line_number: 5, description: "Fee", quantity: null, unit_price: null, amount_minor: 500, tax_rate: null, created_at: "x" },
          ],
        }),
      }),
    );
    renderReview();
    expect(await screen.findByText(/Printed \$54\.00\./)).toBeInTheDocument();
    expect(screen.getByText(/10 × \$4\.50 is \$45\.00\./)).toBeInTheDocument();
    expect(screen.getByText(/2 × \$3\.00 = \$6\.00/)).toBeInTheDocument();
    expect(screen.getByText("Not checked: needs a quantity, a price and an amount.")).toBeInTheDocument();
  });

  it("puts printed and calculated totals side by side with the difference", async () => {
    install(
      detailFixture({
        checks: checksFixture({
          SUBTOTAL_MATCH: failing("SUBTOTAL_MATCH", { lines_sum: 21200, stated: 21500, lines_without_amount: 0 }),
          TOTAL_MATCH: failing("TOTAL_MATCH", { expected: 23550, stated: 23650 }),
        }),
        entry: entryFixture({ subtotal_minor: 21500, total_minor: 23650 }),
      }),
    );
    renderReview();
    expect(await screen.findByText("Printed $236.50, calculated $235.50, difference $1.00")).toBeInTheDocument();
    expect(screen.getByText("Printed $215.00, calculated $212.00, difference $3.00")).toBeInTheDocument();
  });

  it("locks everything once approved, with Reopen offered", async () => {
    const fake = install(
      detailFixture({ document: { ...detailFixture().document, status: "approved" } }),
      { responders: [(c) => (c.path === "/api/documents/5/reopen" ? Response.json({ document: detailFixture().document, review: {} }) : undefined)] },
    );
    renderReview();
    expect(await screen.findByText("Approved. Reopen it to make changes.")).toBeInTheDocument();
    expect(screen.getByLabelText("Invoice number")).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "Approve entry" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add a line" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));
    await waitFor(() => expect(fake.sent("POST", "/api/documents/5/reopen")).toHaveLength(1));
  });

  it("explains that an exported entry cannot be reopened", async () => {
    install(detailFixture({ document: { ...detailFixture().document, status: "exported" } }));
    renderReview();
    expect(await screen.findByText("This entry was exported, so it can no longer be changed.")).toBeInTheDocument();
    expect(screen.getByText(/Exported entries cannot be reopened/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).toBeNull();
  });
});

describe("the vendor", () => {
  it("shows the match in words and suggests close names without applying them", async () => {
    const fake = install(detailFixture({ checks: unknownVendor() }), {
      vendors: [
        { id: 3, name: "Brightway Supply Co.", default_category: null, default_currency: null, is_active: true, aliases: [] },
        { id: 4, name: "Lakeside Hardware", default_category: null, default_currency: null, is_active: true, aliases: [] },
      ],
      suggestions: [{ vendor_id: 3, name: "Brightway Supply Co.", score: 0.93 }],
    });
    renderReview();
    expect(await screen.findByText("Unknown vendor")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pick vendor…" }));
    const dialog = await screen.findByRole("dialog", { name: "Pick the vendor" });
    expect(await within(dialog).findByRole("button", { name: "Probably the same: Brightway Supply Co." })).toBeInTheDocument();
    expect(fake.sent("POST", "/api/entries/1/vendor")).toHaveLength(0); // nothing was chosen for you
    fireEvent.change(within(dialog).getByLabelText("Search your vendors"), { target: { value: "lake" } });
    expect(within(dialog).getByRole("button", { name: "Lakeside Hardware" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Brightway Supply Co." })).toBeNull();
  });

  it("chooses an existing vendor", async () => {
    const chosen = detailFixture({ entry: entryFixture({ vendor_id: 3, vendor_name: "Brightway Supply Co.", vendor_match_method: "manual" }) });
    const fake = install(detailFixture({ checks: unknownVendor() }), {
      vendors: [{ id: 3, name: "Brightway Supply Co.", default_category: null, default_currency: null, is_active: true, aliases: [] }],
      responders: [(c) => (c.path === "/api/entries/1/vendor" && c.method === "POST" ? Response.json(chosen) : undefined)],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Pick vendor…" }));
    fireEvent.click(await screen.findByRole("button", { name: "Brightway Supply Co." }));
    await waitFor(() => expect(fake.sent("POST", "/api/entries/1/vendor")).toHaveLength(1));
    expect(fake.sent("POST", "/api/entries/1/vendor")[0].body).toEqual({ vendor_id: 3, create: false });
    expect(await screen.findByText("Vendor set to Brightway Supply Co..")).toBeInTheDocument();
    expect(screen.getByText("Chosen by you")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("creates a vendor from the printed name", async () => {
    const created = detailFixture({ entry: entryFixture({ vendor_id: 9, vendor_name: "Brightway Supply", vendor_match_method: "created" }) });
    const fake = install(detailFixture({ checks: unknownVendor() }), {
      responders: [(c) => (c.path === "/api/entries/1/vendor" && c.method === "POST" ? Response.json(created) : undefined)],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Pick vendor…" }));
    fireEvent.click(await screen.findByRole("button", { name: "Create vendor “Brightway Supply”" }));
    await waitFor(() => expect(fake.sent("POST", "/api/entries/1/vendor")).toHaveLength(1));
    expect(fake.sent("POST", "/api/entries/1/vendor")[0].body).toEqual({ create: true });
  });

  it("explains a refusal inside the dialog and keeps it open", async () => {
    install(detailFixture({ checks: unknownVendor() }), {
      responders: [
        (c) =>
          c.path === "/api/entries/1/vendor" && c.method === "POST"
            ? Response.json({ error: { code: "vendor_exists", message: "A vendor with that name already exists.", request_id: "r" } }, { status: 409 })
            : undefined,
      ],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Pick vendor…" }));
    fireEvent.click(await screen.findByRole("button", { name: "Create vendor “Brightway Supply”" }));
    expect(await screen.findByText("A vendor with that name already exists.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Pick the vendor" })).toBeInTheDocument();
  });
});

describe("rejecting, duplicates and reprocessing", () => {
  it("rejects with a reason", async () => {
    const fake = install(detailFixture(), {
      queue: [5, 6],
      responders: [(c) => (c.path === "/api/documents/5/reject" ? Response.json({ document: detailFixture().document, review: {} }) : undefined)],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Reject…" }));
    const dialog = screen.getByRole("dialog", { name: "Reject this document" });
    expect(within(dialog).getByRole("button", { name: "Reject document" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Unreadable" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Reject document" }));
    await waitFor(() => expect(fake.sent("POST", "/api/documents/5/reject")).toHaveLength(1));
    expect(fake.sent("POST", "/api/documents/5/reject")[0].body).toMatchObject({ reason: "Unreadable" });
    expect(await screen.findByText("Rejected.")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/review/6");
  });

  it("finds the other document, shows both side by side, and marks the duplicate", async () => {
    const fake = install(detailFixture(), {
      queue: [5, 6],
      responders: [(c) => (c.path === "/api/documents/5/mark-duplicate" ? Response.json({ document: detailFixture().document, review: {} }) : undefined)],
    });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Mark as duplicate of…" }));
    fireEvent.change(screen.getByLabelText(/Find the other document/), { target: { value: "north" } });
    fireEvent.click(await screen.findByRole("button", { name: /doc-40\.pdf · Northfield · INV-40/ }));
    expect(screen.getByText("This document")).toBeInTheDocument();
    expect(screen.getByText("The other document")).toBeInTheDocument();
    expect(screen.getByText("INV-40")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mark as duplicate" }));
    await waitFor(() => expect(fake.sent("POST", "/api/documents/5/mark-duplicate")).toHaveLength(1));
    expect(fake.sent("POST", "/api/documents/5/mark-duplicate")[0].body).toMatchObject({ duplicate_of: 40 });
  });

  it("reprocesses from the chosen stage", async () => {
    const fake = install(detailFixture(), { responders: [(c) => (c.path === "/api/documents/5/reprocess" ? Response.json(detailFixture().document) : undefined)] });
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "Reprocess…" }));
    fireEvent.click(screen.getByLabelText(/Read the page again/));
    fireEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    await waitFor(() => expect(fake.sent("POST", "/api/documents/5/reprocess")).toHaveLength(1));
    expect(fake.sent("POST", "/api/documents/5/reprocess")[0].body).toEqual({ from_stage: "read" });
  });

  it("shows the history in words: reads, your changes, decisions", async () => {
    install(
      detailFixture({
        history: [
          { event_type: "stage_finished", stage: "read", from_status: null, to_status: null, payload: {}, duration_ms: 2500, created_at: "2026-03-14T10:00:01.000Z" },
          { event_type: "check_failed", stage: "check", from_status: null, to_status: null, payload: { check: "UNKNOWN_VENDOR", passed: false }, duration_ms: null, created_at: "2026-03-14T10:00:05.000Z" },
        ],
        edits: [{ id: 1, entry_id: 1, line_id: null, field: "total", old_value: "23650", new_value: "80000", reviewer: "local", created_at: "2026-03-14T10:01:00.000Z" }],
        reviews: [{ id: 1, document_id: 5, decision: "reject", reason: "Not ours", edited: true, overrides: 0, reviewer: "local", review_seconds: 61, created_at: "2026-03-14T10:02:00.000Z" }],
      }),
    );
    renderReview();
    fireEvent.click(await screen.findByRole("button", { name: "History" }));
    const dialog = screen.getByRole("dialog", { name: "History" });
    expect(within(dialog).getByText("Page read (2.5 s)")).toBeInTheDocument();
    expect(within(dialog).getByText("Check failed: New vendor")).toBeInTheDocument();
    expect(within(dialog).getByText("You changed total: $236.50 → $800.00")).toBeInTheDocument();
    expect(within(dialog).getByText("Rejected (“Not ours”, 61 s)")).toBeInTheDocument();
  });
});

describe("keyboard", () => {
  const press = (key: string, target: Element = document.body) => fireEvent.keyDown(target, { key });
  // The shortcut listener is attached in an effect after the screen first shows the document, so
  // a key pressed the moment the screen appears can be lost. Let pending effects run first.
  const settled = () => act(async () => undefined);

  it("j and k move through the documents waiting", async () => {
    install(detailFixture(), { queue: [4, 5, 6] });
    renderReview();
    await screen.findByText(/2 of 3 waiting/);
    await settled();
    press("j");
    expect(window.location.hash).toBe("#/review/6");
    window.location.hash = "#/review/5";
    press("k");
    expect(window.location.hash).toBe("#/review/4");
  });

  it("a approves only when allowed, r asks for a reason, ? lists the shortcuts", async () => {
    const fake = install(detailFixture({ checks: unknownVendor() }), { queue: [5] });
    renderReview();
    await screen.findByRole("button", { name: "Approve entry" });
    await settled();
    press("a");
    expect(fake.sent("POST", "/api/documents/5/approve")).toHaveLength(0);
    press("r");
    expect(screen.getByRole("dialog", { name: "Reject this document" })).toBeInTheDocument();
    cleanup();
    install(detailFixture(), { queue: [5] });
    renderReview();
    await screen.findByRole("button", { name: "Approve entry" });
    await settled();
    press("?");
    expect(screen.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument();
  });

  it("g then p moves to the page picture and e to the first field", async () => {
    install(detailFixture());
    renderReview();
    await screen.findByRole("button", { name: "Approve entry" });
    await settled();
    press("g");
    press("p");
    expect(screen.getByRole("region", { name: "Page picture, scrollable" })).toHaveFocus();
    press("e");
    expect(screen.getByLabelText("Invoice number")).toHaveFocus();
  });

  it("does nothing while you are typing, or while a dialog is open", async () => {
    install(detailFixture(), { queue: [4, 5, 6] });
    renderReview();
    const box = await screen.findByLabelText("Invoice number");
    await settled();
    press("j", box);
    press("r", box);
    expect(window.location.hash).toBe("#/review/5");
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    press("j");
    expect(window.location.hash).toBe("#/review/5");
  });

  it("ignores keys with a modifier held", async () => {
    install(detailFixture(), { queue: [4, 5, 6] });
    renderReview();
    await screen.findByText(/2 of 3 waiting/);
    await settled();
    fireEvent.keyDown(document.body, { key: "j", ctrlKey: true });
    expect(window.location.hash).toBe("#/review/5");
  });
});

describe("a phone", () => {
  it("has tabs for the page, the details and the checks", async () => {
    install(detailFixture({ checks: unknownVendor() }));
    const { container } = renderReview();
    const group = await screen.findByRole("group", { name: "Show" });
    expect(within(group).getByRole("button", { name: "Details" })).toHaveAttribute("aria-pressed", "true");
    expect(within(group).getByRole("button", { name: "Checks (1)" })).toBeInTheDocument();
    fireEvent.click(within(group).getByRole("button", { name: "Page" }));
    expect(container.querySelector(".review")?.getAttribute("data-tab")).toBe("page");
    fireEvent.click(within(group).getByRole("button", { name: "Checks (1)" }));
    expect(container.querySelector(".review")?.getAttribute("data-tab")).toBe("checks");
  });

  it("'Show on page' switches to the page, 'Fix value' to the details", async () => {
    install(detailFixture({ checks: checksFixture({ TOTAL_MATCH: failing("TOTAL_MATCH", { expected: 1, stated: 2 }) }) }));
    const { container } = renderReview();
    await screen.findByText("Must be resolved before approving");
    const checks = within(screen.getByRole("region", { name: "Checks" }));
    fireEvent.click(checks.getByRole("button", { name: "Show on page" }));
    expect(container.querySelector(".review")?.getAttribute("data-tab")).toBe("page");
    fireEvent.click(checks.getByRole("button", { name: "Go to the value" }));
    expect(container.querySelector(".review")?.getAttribute("data-tab")).toBe("details");
  });
});

describe("what leaves the screen", () => {
  it("never puts document text in the address", async () => {
    install(detailFixture({ entry: entryFixture({ vendor_name_raw: "Secret Vendor Ltd" }), checks: unknownVendor() }));
    renderReview();
    await screen.findByRole("heading", { level: 1 });
    act(() => {
      press("g");
    });
    expect(window.location.href).not.toContain("Secret");
  });

  function press(key: string) {
    fireEvent.keyDown(document.body, { key });
  }
});
