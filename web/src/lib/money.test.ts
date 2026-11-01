import { describe, expect, it } from "vitest";

import { formatMinor } from "./money";

describe("formatMinor", () => {
  it("writes dollars and cents with grouping and a symbol", () => {
    expect(formatMinor(15200, "USD")).toBe("$152.00");
    expect(formatMinor(5, "USD")).toBe("$0.05");
    expect(formatMinor(0, "USD")).toBe("$0.00");
    expect(formatMinor(124005, "USD")).toBe("$1,240.05");
    expect(formatMinor(123456789, "EUR")).toBe("€1,234,567.89");
  });

  it("never loses a cent to floating point", () => {
    // 0.1 + 0.2 style traps: these are exact because the digits are split as integers
    expect(formatMinor(30, "USD")).toBe("$0.30");
    expect(formatMinor(10_000_000_000_001, "USD")).toBe("$100,000,000,000.01");
  });

  it("uses no decimals for currencies without a minor unit", () => {
    expect(formatMinor(1500, "JPY")).toBe("¥1,500");
  });

  it("shows a credit note as negative with a real minus sign", () => {
    expect(formatMinor(15200, "USD", { credit: true })).toBe("−$152.00");
    expect(formatMinor(0, "USD", { credit: true })).toBe("$0.00"); // never minus zero
    expect(formatMinor(-500, "USD")).toBe("−$5.00");
  });

  it("writes an unknown currency by its code, and nothing for nothing", () => {
    expect(formatMinor(1000, "CHF")).toBe("CHF 10.00");
    expect(formatMinor(null, "USD")).toBe("");
    expect(formatMinor(undefined, "USD")).toBe("");
  });

  it("can leave the symbol off", () => {
    expect(formatMinor(15200, "USD", { bare: true })).toBe("152.00");
  });
});
