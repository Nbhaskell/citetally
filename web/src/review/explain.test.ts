import { describe, expect, it } from "vitest";

import type { CheckCode, CheckOut, Evidence } from "../api/client";
import { explain } from "./explain";
import { entryFixture } from "./fixtures";

function check(code: CheckCode, detail: Record<string, unknown>, blocking = true): CheckOut {
  return {
    check_code: code,
    blocking,
    passed: false,
    detail,
    overridden: false,
    override_reason: null,
    overridden_at: null,
  };
}

const none: Evidence[] = [];

describe("explain", () => {
  it("says a line does not add up with the numbers, as in the brief", () => {
    const said = explain(check("LINE_MATH", { mismatches: [{ line: 3, expected: 4500, stated: 5400 }] }), entryFixture(), none);
    expect(said.title).toBe("A line doesn't add up");
    expect(said.text).toEqual(["Line 3: 10 × $4.50 is $45.00, but the page says $54.00."]);
    expect(said.target).toBe("amount:11");
  });

  it("explains the subtotal, tax and total with printed and calculated figures", () => {
    const entry = entryFixture();
    expect(explain(check("SUBTOTAL_MATCH", { lines_sum: 21200, stated: 21500, lines_without_amount: 0 }), entry, none).text).toEqual([
      "The lines add up to $212.00. The page says the subtotal is $215.00.",
    ]);
    expect(explain(check("TAX_MATCH", { rate_printed: true, expected: 1696, stated: 1996 }), entry, none).text[0]).toBe(
      "8% tax comes to $16.96. The page says $19.96.",
    );
    expect(explain(check("TOTAL_MATCH", { expected: 23550, stated: 23650 }), entry, none).text).toEqual([
      "Subtotal + tax + shipping − discount is $235.50. The page says $236.50.",
    ]);
  });

  it("asks for lines that have no amount to be filled in rather than guessing a sum", () => {
    const said = explain(check("SUBTOTAL_MATCH", { lines_sum: 100, stated: 100, lines_without_amount: 2 }), entryFixture(), none);
    expect(said.text[0]).toMatch(/no amount/);
  });

  it("names what is missing and the rule for the document type", () => {
    const one = explain(check("REQUIRED_FIELDS", { missing: ["invoice_number"] }), entryFixture(), none);
    expect(one.text[0]).toBe("Invoice number is missing.");
    expect(one.text[1]).toBe("Invoices need a vendor, an invoice number, a date, a total and a category.");
    expect(one.target).toBe("invoice_number");
    const many = explain(check("REQUIRED_FIELDS", { missing: ["vendor_name", "total", "category"] }), entryFixture({ entry_type: "receipt" }), none);
    expect(many.text[0]).toBe("Missing: vendor, total and category.");
    expect(many.text[1]).toMatch(/^Receipts need/);
    expect(many.pickVendor).toBe(true);
  });

  it("quotes what could not be found, and says how many more", () => {
    const entry = entryFixture();
    const missing = [1, 2, 3, 4, 5].map((n) => ({ field: "total", line: null, printed: `$${n}.00` }));
    const said = explain(check("VALUE_IN_DOCUMENT", { not_found: missing }), entry, none);
    expect(said.text[0]).toContain("'$1.00', '$2.00' and '$3.00' and 2 more");
    expect(said.text[0]).toContain("Check against the page.");
    expect(said.target).toBe("total");
    const line = explain(check("VALUE_IN_DOCUMENT", { not_found: [{ field: "amount", line: 3, printed: "$54.00" }] }), entry, none);
    expect(line.text[0]).toBe("We couldn't find '$54.00' on the page. It may have been misread. Check against the page.");
    expect(line.target).toBe("amount:11");
  });

  it("links the other document for a duplicate", () => {
    const said = explain(check("DUPLICATE_SUSPECT", { matches: [{ document_id: 12, reason: "invoice_number" }] }), entryFixture(), none);
    expect(said.documents).toEqual([12]);
    expect(said.text[0]).toBe("Same vendor and invoice number as another document.");
    const other = explain(check("DUPLICATE_SUSPECT", { matches: [{ document_id: 7, reason: "vendor_total_date" }] }), entryFixture(), none);
    expect(other.text[0]).toMatch(/total and a nearby date/);
  });

  it("offers the vendor picker for an unknown vendor, using the printed name as text", () => {
    const said = explain(check("UNKNOWN_VENDOR", {}), entryFixture({ vendor_name_raw: "<b>Brightway</b>" }), none);
    expect(said.text[0]).toBe("'<b>Brightway</b>' isn't in your vendor list. Pick an existing vendor or add it.");
    expect(said.pickVendor).toBe(true);
    expect(explain(check("UNKNOWN_VENDOR", {}), entryFixture({ vendor_name_raw: null }), none).text[0]).toMatch(/No vendor was read/);
  });

  it("writes an outlier as a ratio of the vendor's usual", () => {
    const high = explain(check("AMOUNT_OUTLIER", { direction: "high", median: "5000", stated: 21000 }, false), entryFixture(), none);
    expect(high.text[0]).toBe("This is 4.2 times this vendor's usual invoice (larger).");
    const low = explain(check("AMOUNT_OUTLIER", { direction: "low", median: "6000", stated: 1500 }, false), entryFixture(), none);
    expect(low.text[0]).toBe("This is 4.0 times this vendor's usual invoice (smaller).");
  });

  it("explains each date problem, currency, read quality and ambiguity", () => {
    const entry = entryFixture();
    expect(explain(check("DATE_SANITY", { problems: ["in_the_future"] }, false), entry, none).text).toEqual([
      "The invoice date is in the future (14 Mar 2026).",
    ]);
    const both = explain(check("DATE_SANITY", { problems: ["due_before_entry", "too_old"] }, false), entry, none);
    expect(both.text).toContain("The due date is before the invoice date.");
    expect(both.target).toBe("due_date");
    expect(explain(check("CURRENCY_CHECK", { stated: "EUR", usual: "USD" }, false), entry, none).text[0]).toBe(
      "This invoice is in EUR. Your usual is USD.",
    );
    const blurry = explain(check("LOW_READ_QUALITY", { reasons: ["low_confidence", "large_skew"] }, false), entry, none);
    expect(blurry.text[0]).toBe("This scan is hard to read, so check every number against the page.");
    expect(blurry.text).toContain("The page was photographed at a steep angle.");
    const evidence = [{ field: "entry_date", printed_text: "03/04/2026" } as Evidence];
    const ambiguous = explain(
      check("AMBIGUOUS_FORMAT", { ambiguous: [{ field: "entry_date", line: null, readings: ["2026-03-04", "2026-04-03"] }] }, false),
      entry,
      evidence,
    );
    expect(ambiguous.text[0]).toBe("'03/04/2026' could be read as 4 Mar 2026 and 3 Apr 2026. We read it as the first.");
  });

  it("says the page contains instructions without quoting them", () => {
    const said = explain(check("SUSPICIOUS_TEXT", { matches: [{ pattern: "ignore_instructions", page: 1 }] }, false), entryFixture(), none);
    expect(said.text).toEqual(["The page includes text addressed to a reader or system. It was ignored. Review as usual."]);
  });

  it("says which rate the page prints when no combination of the lines gives the tax", () => {
    const said = explain(
      check("TAX_MATCH", { rate_printed: false, stated: 500, printed_rate: "0.07", most: 1050, reachable: false }, false),
      entryFixture({ lines: [] }),
      none,
    );
    expect(said.text).toEqual([
      "The page prints a 7% tax rate. $5.00 is not 7% of any of the lines, with or without shipping and discount.",
    ]);
  });

  it("says what the printed rate allows at most when the tax is above it", () => {
    const said = explain(
      check("TAX_MATCH", { rate_printed: false, stated: 900, printed_rate: "0.07", most: 700 }, false),
      entryFixture({ lines: [] }),
      none,
    );
    expect(said.text).toEqual(["The page prints a 7% tax rate, which allows at most $7.00. The page says $9.00."]);
  });

  it("shows a vendor-rate note when the tax rate is unusual", () => {
    const said = explain(
      check("TAX_MATCH", { rate_printed: false, stated: 1500, implied_rate: "0.1500", usual_rate: "0.0800", unusual: true }, false),
      entryFixture({ lines: [] }),
      none,
    );
    expect(said.text[1]).toContain("usual rate is 0.0800");
  });
});
