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

import { amountInput, formatDecimal, parseMinor, percentText, priceText } from "./money";

describe("parseMinor", () => {
  it.each([
    ["152.00", 15200],
    ["152", 15200],
    ["152.5", 15250],
    ["$1,240.05", 124005],
    ["1240.05", 124005],
    ["0.05", 5],
    ["USD 12.30", 1230],
    ["  7  ", 700],
  ])("reads %s as %i minor units", (text, minor) => {
    expect(parseMinor(text, "USD")).toEqual({ ok: true, minor });
  });

  it("treats empty as clearing the value", () => {
    expect(parseMinor("  ", "USD")).toEqual({ ok: true, minor: null });
  });

  it.each(["12.345", "1,24.00", "abc", "12..3", "1e5", "$", "12,5", "1 240.00", "-5", "−5.00"])(
    "refuses %s rather than guess",
    (text) => {
      const result = parseMinor(text, "USD");
      expect(result.ok).toBe(false);
    },
  );

  it("never goes through a float: large amounts stay exact", () => {
    expect(parseMinor("99,999,999,999.99", "USD")).toEqual({ ok: true, minor: 9999999999999 });
    expect(parseMinor("100,000,000,001.00", "USD").ok).toBe(false);
  });

  it("reads whole-unit currencies as whole numbers", () => {
    expect(parseMinor("1,500", "JPY")).toEqual({ ok: true, minor: 1500 });
    expect(parseMinor("1500.5", "JPY").ok).toBe(false);
  });
});

describe("amountInput, percentText, priceText", () => {
  it("writes an amount box value without symbol or grouping", () => {
    expect(amountInput(124005, "USD")).toBe("1240.05");
    expect(amountInput(null, "USD")).toBe("");
    expect(amountInput(1500, "JPY")).toBe("1500");
  });

  it("reads back what parseMinor accepted", () => {
    for (const minor of [0, 5, 15200, 124005, 9999999999999]) {
      expect(parseMinor(amountInput(minor, "USD"), "USD")).toEqual({ ok: true, minor });
    }
  });

  it("turns a stored fraction into a percentage exactly", () => {
    expect(percentText("0.0825")).toBe("8.25%");
    expect(percentText("0.07")).toBe("7%");
    expect(percentText("0.1")).toBe("10%");
    expect(percentText("0.0725")).toBe("7.25%");
    expect(percentText("0.00125")).toBe("0.125%");
    expect(percentText("1")).toBe("100%");
    expect(percentText("0")).toBe("0%");
    expect(percentText("bad")).toBe("");
    expect(percentText(null)).toBe("");
  });

  it("puts the symbol in front of a stored price", () => {
    expect(priceText("4.50", "USD")).toBe("$4.50");
    expect(priceText(null, "USD")).toBe("");
  });
});

describe("formatDecimal", () => {
  it("shows a decimal string from the API as money, signed, without rounding", () => {
    expect(formatDecimal("1240.05", "USD")).toBe("$1,240.05");
    expect(formatDecimal("-45.5", "USD")).toBe("−$45.50");
    expect(formatDecimal("12", "USD")).toBe("$12.00");
    expect(formatDecimal("1500", "JPY")).toBe("¥1,500");
    expect(formatDecimal("0.00", "USD")).toBe("$0.00");
  });

  it("leaves text it cannot read as it was", () => {
    expect(formatDecimal("n/a", "USD")).toBe("n/a");
  });
});
