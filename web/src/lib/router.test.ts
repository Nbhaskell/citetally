import { describe, expect, it } from "vitest";

import { hrefFor, parseHash } from "./router";

describe("router", () => {
  it("knows each screen", () => {
    expect(parseHash("")).toEqual({ name: "inbox" });
    expect(parseHash("#/")).toEqual({ name: "inbox" });
    expect(parseHash("#/review/42")).toEqual({ name: "review", id: 42 });
    expect(parseHash("#/vendors")).toEqual({ name: "vendors" });
    expect(parseHash("#/exports/")).toEqual({ name: "exports" });
    expect(parseHash("#/insights")).toEqual({ name: "insights" });
    expect(parseHash("#/settings")).toEqual({ name: "settings" });
  });

  it("sends anything else to not found, including odd ids", () => {
    expect(parseHash("#/nope")).toEqual({ name: "notfound" });
    expect(parseHash("#/review/abc")).toEqual({ name: "notfound" });
    expect(parseHash("#/review/1/../2")).toEqual({ name: "notfound" });
    expect(parseHash("#/review/9999999999")).toEqual({ name: "notfound" });
  });

  it("makes addresses that hold only a screen and an id", () => {
    expect(hrefFor({ name: "review", id: 7 })).toBe("#/review/7");
    expect(hrefFor({ name: "inbox" })).toBe("#/");
    expect(hrefFor({ name: "vendors" })).toBe("#/vendors");
  });
});
