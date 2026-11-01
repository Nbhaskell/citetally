import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { InsightsOut } from "../api/client";
import Insights from "./Insights";

const EMPTY: InsightsOut = {
  date_from: null,
  date_to: null,
  by_category: [],
  by_vendor: [],
  waiting_by_age: [
    { bucket: "under_1_day", documents: 0 },
    { bucket: "1_to_3_days", documents: 0 },
    { bucket: "3_to_7_days", documents: 0 },
    { bucket: "over_7_days", documents: 0 },
  ],
  approved_documents: 0,
  edited_documents: 0,
  edited_fields: [],
  checks_failing: [],
  review_seconds_median: null,
  review_seconds_count: 0,
};

const FULL: InsightsOut = {
  ...EMPTY,
  by_category: [
    { code: "SUPPLIES", label: "Supplies", currency: "USD", total_minor: 124005, entries: 4 },
    { code: "REPAIRS", label: "Repairs", currency: "USD", total_minor: -4550, entries: 1 },
    { code: "SUPPLIES", label: "Supplies", currency: "EUR", total_minor: 9900, entries: 1 },
  ],
  by_vendor: Array.from({ length: 12 }, (_, i) => ({
    code: null,
    label: `Vendor ${i + 1}`,
    currency: "USD",
    total_minor: (12 - i) * 1000,
    entries: 1,
  })),
  waiting_by_age: [
    { bucket: "under_1_day", documents: 3 },
    { bucket: "1_to_3_days", documents: 0 },
    { bucket: "3_to_7_days", documents: 1 },
    { bucket: "over_7_days", documents: 0 },
  ],
  approved_documents: 8,
  edited_documents: 3,
  edited_fields: [
    { field: "total", edits: 2 },
    { field: "po_number", edits: 1 },
  ],
  checks_failing: [{ check_code: "UNKNOWN_VENDOR", documents: 5, overridden: 2 }],
  review_seconds_median: 90,
  review_seconds_count: 7,
};

function install(body: InsightsOut | ((url: URL) => Response)) {
  const urls: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      urls.push(url);
      return typeof body === "function" ? body(url) : Response.json(body);
    }),
  );
  return urls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Insights", () => {
  it("says plainly when there is nothing yet, in every section", async () => {
    install(EMPTY);
    render(<Insights />);
    expect(await screen.findAllByText("Nothing has been approved in this period yet.")).toHaveLength(3);
    expect(screen.getByText("Nothing is waiting.")).toBeInTheDocument();
    expect(screen.getByText("No check is failing.")).toBeInTheDocument();
    expect(screen.getByText("No review time has been recorded in this period yet.")).toBeInTheDocument();
  });

  it("writes every figure out, keeps currencies apart and shows credits with a minus sign", async () => {
    install(FULL);
    render(<Insights />);
    const category = (await screen.findByRole("heading", { name: "Spending by category" })).closest("section") as HTMLElement;
    expect(within(category).getByRole("heading", { name: "USD" })).toBeInTheDocument();
    expect(within(category).getByRole("heading", { name: "EUR" })).toBeInTheDocument();
    expect(category).toHaveTextContent("$1,240.05 (4 entries)");
    expect(category).toHaveTextContent("−$45.50 (1 entry)");
    expect(category).toHaveTextContent("€99.00 (1 entry)");
    expect(category).toHaveTextContent("5 entries in all, $1,194.55. Credit notes are taken off.");
  });

  it("shows the top ten vendors and the rest on request", async () => {
    install(FULL);
    render(<Insights />);
    const vendors = (await screen.findByRole("heading", { name: "Spending by vendor" })).closest("section") as HTMLElement;
    expect(within(vendors).getAllByRole("listitem")).toHaveLength(10);
    fireEvent.click(within(vendors).getByRole("button", { name: "Show all 12" }));
    expect(within(vendors).getAllByRole("listitem")).toHaveLength(12);
  });

  it("offers every list as a table too", async () => {
    install(FULL);
    render(<Insights />);
    const section = (await screen.findByRole("heading", { name: "Checks that fire most" })).closest("section") as HTMLElement;
    expect(section).toHaveTextContent("New vendor");
    fireEvent.click(within(section).getByRole("button", { name: "Show as table" }));
    const table = within(section).getByRole("table", { name: "Checks failing, by how many documents" });
    expect(within(table).getByText("Accepted with a reason")).toBeInTheDocument();
    expect(within(table).getByText("New vendor")).toBeInTheDocument();
    expect(within(table).getAllByRole("cell").map((c) => c.textContent)).toEqual(["New vendor", "5", "2"]);
    fireEvent.click(within(section).getByRole("button", { name: "Show as bars" }));
    expect(within(section).queryByRole("table")).toBeNull();
  });

  it("reports how much needed fixing and the median review time in words", async () => {
    install(FULL);
    render(<Insights />);
    expect(await screen.findByText(/3 of 8 approved documents needed a value changed by hand \(38%\)/)).toBeInTheDocument();
    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getByText("PO number")).toBeInTheDocument();
    expect(screen.getByText("Median: 1 min 30 s")).toBeInTheDocument();
    expect(screen.getByText(/From 7 decisions/)).toBeInTheDocument();
    expect(screen.getByText("Less than a day")).toBeInTheDocument();
    expect(screen.getByText("3 documents")).toBeInTheDocument();
  });

  it("asks again with the dates when the period changes", async () => {
    const urls = install(EMPTY);
    render(<Insights />);
    await screen.findByText("Nothing is waiting.");
    expect(urls[0].search).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Last 30 days" }));
    await waitFor(() => expect(urls.length).toBe(2));
    expect(urls[1].searchParams.get("date_from")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(urls[1].searchParams.get("date_to")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(screen.getByRole("button", { name: "Last 30 days" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows an error with the request id and a way to try again", async () => {
    install(() =>
      Response.json({ error: { code: "internal_error", message: "Broken.", request_id: "req-5" } }, { status: 500 }),
    );
    render(<Insights />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("request req-5");
    expect(within(alert).getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
