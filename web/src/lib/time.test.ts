import { describe, expect, it } from "vitest";

import { age, shortDate } from "./time";

const NOW = new Date("2026-06-15T12:00:00Z");

describe("age", () => {
  it.each([
    ["2026-06-15T11:59:50Z", "just now"],
    ["2026-06-15T11:55:00Z", "5 min"],
    ["2026-06-15T09:00:00Z", "3 h"],
    ["2026-06-12T12:00:00Z", "3 d"],
  ])("%s is %s", (iso, words) => {
    expect(age(iso, NOW)).toBe(words);
  });

  it("never shows a negative age", () => {
    expect(age("2026-06-15T12:30:00Z", NOW)).toBe("just now");
  });
});

describe("shortDate", () => {
  it("writes a printed date without a time zone shift", () => {
    expect(shortDate("2026-03-14")).toBe("14 Mar 2026");
    expect(shortDate("2026-01-01")).toBe("1 Jan 2026");
  });

  it("is empty for nothing or for something that is not a date", () => {
    expect(shortDate(null)).toBe("");
    expect(shortDate("<b>x</b>")).toBe("");
  });
});
