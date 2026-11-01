import { useSyncExternalStore } from "react";

// A tiny hash router. Addresses hold only screen names and document ids, never search text or
// vendor names, so nothing about a document ends up in a URL, a history entry or a log.

export type Route =
  | { name: "inbox" }
  | { name: "review"; id: number }
  | { name: "vendors" }
  | { name: "exports" }
  | { name: "insights" }
  | { name: "settings" }
  | { name: "notfound" };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#\/?/, "").replace(/\/+$/, "");
  if (path === "") return { name: "inbox" };
  const review = /^review\/(\d{1,9})$/.exec(path);
  if (review) return { name: "review", id: Number(review[1]) };
  if (path === "vendors" || path === "exports" || path === "insights" || path === "settings") {
    return { name: path };
  }
  return { name: "notfound" };
}

export function hrefFor(route: Route): string {
  switch (route.name) {
    case "inbox":
      return "#/";
    case "review":
      return `#/review/${route.id}`;
    case "notfound":
      return "#/";
    default:
      return `#/${route.name}`;
  }
}

function subscribe(callback: () => void): () => void {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return parseHash(hash);
}

export function navigate(route: Route): void {
  window.location.hash = hrefFor(route).slice(1);
}
