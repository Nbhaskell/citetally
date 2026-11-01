import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CategoryOut, VendorOut } from "../api/client";
import { ToastProvider } from "../ui/Toast";
import Vendors from "./Vendors";

const CATEGORIES: CategoryOut[] = [
  { code: "SUPPLIES", name: "Supplies", is_active: true },
  { code: "REPAIRS", name: "Repairs", is_active: true },
];

function vendor(id: number, name: string, extra: Partial<VendorOut> = {}): VendorOut {
  return {
    id,
    name,
    default_category: null,
    default_currency: null,
    is_active: true,
    aliases: [],
    entry_count: 0,
    waiting_count: 0,
    last_entry_date: null,
    ...extra,
  };
}

interface Seen {
  method: string;
  path: string;
  body: unknown;
}

function install(vendors: VendorOut[], reply: (seen: Seen) => Response | undefined = () => undefined) {
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
      if (path === "/api/vendors" && method === "GET") return Response.json(vendors);
      if (path === "/api/categories") return Response.json(CATEGORIES);
      return Response.json(vendors[0]);
    }),
  );
  return seen;
}

function renderPage() {
  return render(
    <ToastProvider>
      <Vendors />
    </ToastProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Vendors", () => {
  it("lists vendors with other names, category, entries waiting and the last invoice date", async () => {
    install([
      vendor(1, "Northfield Pet Supply Co.", {
        aliases: ["NPS", "Northfield"],
        default_category: "SUPPLIES",
        entry_count: 7,
        waiting_count: 2,
        last_entry_date: "2026-03-14",
      }),
      vendor(2, "Lakeside Hardware"),
    ]);
    renderPage();
    const row = (await screen.findByText("Northfield Pet Supply Co.")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Also printed as: NPS; Northfield")).toBeInTheDocument();
    expect(within(row).getByRole("combobox", { name: /Default category for Northfield/ })).toHaveValue("SUPPLIES");
    expect(row).toHaveTextContent("7 (2 waiting)");
    expect(row).toHaveTextContent("14 Mar 2026");
  });

  it("shows the empty state, and an error with a way to try again", async () => {
    install([]);
    renderPage();
    expect(await screen.findByText("No vendors yet")).toBeInTheDocument();
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({ error: { code: "internal_error", message: "Broken.", request_id: "req-9" } }, { status: 500 }),
      ),
    );
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("request req-9");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("searches names and other names, and says when nothing matches", async () => {
    install([vendor(1, "Northfield Pet Supply", { aliases: ["NPS"] }), vendor(2, "Lakeside Hardware")]);
    renderPage();
    await screen.findByText("Lakeside Hardware");
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "nps" } });
    expect(screen.queryByText("Lakeside Hardware")).toBeNull();
    expect(screen.getByText("Northfield Pet Supply")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "zzz" } });
    expect(screen.getByText("No vendor matches that")).toBeInTheDocument();
  });

  it("saves a changed default category right away, and can clear it", async () => {
    const seen = install([vendor(1, "Northfield", { default_category: "SUPPLIES" })]);
    renderPage();
    const select = await screen.findByRole("combobox", { name: /Default category for Northfield/ });
    fireEvent.change(select, { target: { value: "REPAIRS" } });
    await waitFor(() => expect(seen.some((s) => s.method === "PATCH")).toBe(true));
    expect(seen.find((s) => s.method === "PATCH")).toMatchObject({
      path: "/api/vendors/1",
      body: { default_category: "REPAIRS" },
    });
    fireEvent.change(select, { target: { value: "" } });
    await waitFor(() => expect(seen.filter((s) => s.method === "PATCH")).toHaveLength(2));
    expect(seen.filter((s) => s.method === "PATCH")[1].body).toEqual({ default_category: null });
  });

  it("adds a vendor, and shows a refusal in the dialog", async () => {
    const seen = install([vendor(1, "Northfield")], (call) =>
      call.method === "POST" && call.path === "/api/vendors"
        ? Response.json(
            { error: { code: "vendor_exists", message: "A vendor or alias with that name already exists.", request_id: "r" } },
            { status: 409 },
          )
        : undefined,
    );
    renderPage();
    await screen.findByText("Northfield");
    fireEvent.click(screen.getAllByRole("button", { name: "Add a vendor" })[0]);
    const dialog = screen.getByRole("dialog", { name: "Add a vendor" });
    const add = within(dialog).getByRole("button", { name: "Add vendor" });
    expect(add).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Vendor name"), { target: { value: "  Northfield  " } });
    fireEvent.change(within(dialog).getByRole("combobox"), { target: { value: "REPAIRS" } });
    fireEvent.click(add);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already exists");
    expect(seen.find((s) => s.method === "POST")?.body).toEqual({ name: "Northfield", default_category: "REPAIRS" });
  });

  it("adds another name for a vendor", async () => {
    const seen = install([vendor(1, "Northfield")]);
    renderPage();
    await screen.findByText("Northfield");
    fireEvent.click(screen.getByRole("button", { name: "Add another name" }));
    const dialog = screen.getByRole("dialog", { name: "Add another name for Northfield" });
    fireEvent.change(within(dialog).getByLabelText("Name as printed"), { target: { value: "N. Pet Supply" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add name" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(seen.find((s) => s.path === "/api/vendors/1/aliases")?.body).toEqual({ alias: "N. Pet Supply" });
  });

  it("spells out what a merge will do before it happens, and only then merges", async () => {
    const seen = install([
      vendor(1, "Northfield Supply", { aliases: ["NPS"], entry_count: 3, waiting_count: 1 }),
      vendor(2, "Northfield Pet Supply"),
    ]);
    renderPage();
    const row = (await screen.findByText("Northfield Supply")).closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Merge…" }));
    const dialog = screen.getByRole("dialog", { name: "Merge Northfield Supply into another vendor" });
    const confirm = within(dialog).getByRole("button", { name: "Merge" });
    expect(confirm).toBeDisabled();
    expect(within(dialog).queryByRole("option", { name: "Northfield Supply" })).toBeNull();
    fireEvent.change(within(dialog).getByRole("combobox"), { target: { value: "2" } });
    const preview = within(dialog).getByRole("status");
    expect(preview).toHaveTextContent("3 entries will move to Northfield Pet Supply.");
    expect(preview).toHaveTextContent("1 entry is still waiting for review and will be checked again.");
    expect(preview).toHaveTextContent("Northfield Supply and its 1 other name will become names of Northfield Pet Supply.");
    expect(preview).toHaveTextContent("will be switched off");
    expect(preview).toHaveTextContent("This cannot be undone from this screen.");
    expect(seen.some((s) => s.path.endsWith("/merge"))).toBe(false);
    fireEvent.click(within(dialog).getByRole("button", { name: "Merge into Northfield Pet Supply" }));
    await waitFor(() => expect(seen.find((s) => s.path === "/api/vendors/1/merge")?.body).toEqual({ into: 2 }));
  });

  it("shows vendor names as text, never as markup", async () => {
    install([vendor(1, "<b>Bold</b> & Sons", { aliases: ["<script>x</script>"] })]);
    renderPage();
    expect(await screen.findByText("<b>Bold</b> & Sons")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
});
