import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SelfTestOut, SettingsOut } from "../api/client";
import { ToastProvider } from "../ui/Toast";
import Settings from "./Settings";

const VALUES: SettingsOut["values"] = {
  default_currency: "USD",
  locale: "en-US",
  duplicate_date_window_days: 7,
  outlier_ratio: "3",
  low_confidence: 75,
};

function settings(overrides: Partial<SettingsOut> = {}): SettingsOut {
  return {
    status: {
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
    },
    allow_hosted: false,
    extract_mode: "text_only",
    values: VALUES,
    defaults: VALUES,
    locales: ["en-GB", "en-US"],
    ...overrides,
  };
}

interface Seen {
  method: string;
  path: string;
  body: unknown;
}

function install(initial: SettingsOut, reply: (seen: Seen) => Response | undefined = () => undefined) {
  let current = initial;
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
      if (path === "/api/settings" && method === "PATCH") {
        current = { ...current, values: { ...current.values, ...(body as object) } };
      }
      return Response.json(current);
    }),
  );
  return seen;
}

function renderPage() {
  return render(
    <ToastProvider>
      <Settings />
    </ToastProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Settings: set-up facts", () => {
  it("shows the read-only facts first, in words", async () => {
    install(settings());
    renderPage();
    const facts = (await screen.findByRole("heading", { name: "How Citetally is set up" })).closest("section") as HTMLElement;
    expect(facts).toHaveTextContent("On this computer (Ollama): qwen3:8b");
    expect(facts).toHaveTextContent("Picture modelNot used");
    expect(facts).toHaveTextContent("Reading modeText only");
    expect(facts).toHaveTextContent("DatabaseWorking");
    expect(facts).toHaveTextContent("Demo dataYes");
    expect(within(facts).queryByRole("status")).toBeNull(); // no hosted warning when hosted is not allowed
  });

  it("says when the scanner or database is missing", async () => {
    const base = settings();
    install({ ...base, status: { ...base.status, ocr_available: false, database_ok: false } });
    renderPage();
    expect(await screen.findByText(/not found on this computer/)).toBeInTheDocument();
    expect(screen.getByText("Problem: it cannot be opened")).toBeInTheDocument();
  });

  it("shows the data-handling warning only when hosted models are allowed", async () => {
    const base = settings();
    install({ ...base, allow_hosted: true });
    renderPage();
    expect(await screen.findByText("Hosted models are allowed here but are not in use.")).toBeInTheDocument();
    expect(screen.getByText(/sent to a third party/)).toBeInTheDocument();
    cleanup();
    install({ ...base, allow_hosted: true, status: { ...base.status, hosted_mode: true } });
    renderPage();
    expect(await screen.findByText("A hosted model is in use.")).toBeInTheDocument();
  });
});

describe("Settings: changing them", () => {
  it("keeps Save off until something changes, then sends only what changed", async () => {
    const seen = install(settings());
    renderPage();
    const save = await screen.findByRole("button", { name: "Save settings" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Duplicate window (days)"), { target: { value: "14" } });
    fireEvent.change(screen.getByLabelText("Date and number order"), { target: { value: "en-GB" } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(seen.some((s) => s.method === "PATCH")).toBe(true));
    expect(seen.find((s) => s.method === "PATCH")?.body).toEqual({ locale: "en-GB", duplicate_date_window_days: 14 });
    expect(await screen.findByText(/Settings saved/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled());
  });

  it("explains a value that cannot be right before asking the server", async () => {
    const seen = install(settings());
    renderPage();
    await screen.findByRole("button", { name: "Save settings" });
    fireEvent.change(screen.getByLabelText("Duplicate window (days)"), { target: { value: "ten" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("whole number of days, from 0 to 60");
    fireEvent.change(screen.getByLabelText("Duplicate window (days)"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Hard-to-read threshold"), { target: { value: "150" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("from 1 to 99");
    expect(seen.some((s) => s.method === "PATCH")).toBe(false);
  });

  it("shows the server's reason when it refuses a value", async () => {
    install(settings(), (call) =>
      call.method === "PATCH"
        ? Response.json(
            { error: { code: "invalid_setting", message: "outlier_ratio: The outlier ratio is a number above 1, up to 100.", request_id: "r" } },
            { status: 422 },
          )
        : undefined,
    );
    renderPage();
    fireEvent.change(await screen.findByLabelText("Unusual amount ratio"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("a number above 1, up to 100");
    expect(screen.getByLabelText("Unusual amount ratio")).toHaveValue("1"); // what was typed is kept
  });

  it("offers a way back to the environment's value and undoes unsaved changes", async () => {
    install(settings({ values: { ...VALUES, low_confidence: 60 } }));
    renderPage();
    const field = await screen.findByLabelText("Hard-to-read threshold");
    expect(field).toHaveValue("60");
    fireEvent.click(screen.getByRole("button", { name: "Back to 75" }));
    expect(field).toHaveValue("75");
    fireEvent.click(screen.getByRole("button", { name: "Undo changes" }));
    expect(field).toHaveValue("60");
  });

  it("writes the currency in capitals", async () => {
    install(settings());
    renderPage();
    const field = await screen.findByLabelText("Default currency");
    fireEvent.change(field, { target: { value: "eur" } });
    expect(field).toHaveValue("EUR");
  });
});

describe("Settings: the self-test", () => {
  const PASSING: SelfTestOut = {
    passed: true,
    results: [
      { name: "A clean invoice", expectation: "Every check passes.", passed: true, fired: [] },
      { name: "A total that is wrong", expectation: "The total does not match.", passed: true, fired: ["TOTAL_MATCH"] },
    ],
  };

  it("runs on request and lists each sample with a word as well as a mark", async () => {
    const seen = install(settings(), (call) => (call.path === "/api/self-test" ? Response.json(PASSING) : undefined));
    renderPage();
    expect(screen.queryByRole("list", { name: "Sample results" })).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "Run checks on sample documents" }));
    expect(await screen.findByText("All 2 samples came out as expected.")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Sample results" });
    expect(within(list).getAllByText("As expected")).toHaveLength(2);
    expect(list).toHaveTextContent("Failed: Total doesn't add up.");
    expect(list).toHaveTextContent("No check failed.");
    expect(seen.filter((s) => s.path === "/api/self-test")).toHaveLength(1);
  });

  it("says which sample did not come out as expected", async () => {
    const failing: SelfTestOut = {
      passed: false,
      results: [{ ...PASSING.results[0] }, { ...PASSING.results[1], passed: false, fired: [] }],
    };
    install(settings(), (call) => (call.path === "/api/self-test" ? Response.json(failing) : undefined));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Run checks on sample documents" }));
    expect(await screen.findByText("1 of 2 samples did not come out as expected.")).toBeInTheDocument();
    expect(screen.getByText("Not as expected")).toBeInTheDocument();
  });

  it("shows an error when the self-test cannot run", async () => {
    install(settings(), (call) =>
      call.path === "/api/self-test"
        ? Response.json({ error: { code: "internal_error", message: "Broken.", request_id: "r" } }, { status: 500 })
        : undefined,
    );
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Run checks on sample documents" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Broken.");
  });
});
