import { useEffect, useRef, type ReactNode } from "react";

import { api, ApiError, UNREACHABLE } from "../api/client";
import { hrefFor, useRoute, type Route } from "../lib/router";
import { useApi } from "../lib/useApi";
import Banner from "../ui/Banner";
import EmptyState from "../ui/EmptyState";
import Skeleton from "../ui/Skeleton";

const NAV: { route: Route; label: string }[] = [
  { route: { name: "inbox" }, label: "Inbox" },
  { route: { name: "vendors" }, label: "Vendors" },
  { route: { name: "exports" }, label: "Exports" },
  { route: { name: "insights" }, label: "Insights" },
  { route: { name: "settings" }, label: "Settings" },
];

function section(route: Route): string {
  return route.name === "review" || route.name === "notfound" ? "inbox" : route.name;
}

const TITLE: Record<string, string> = {
  inbox: "Inbox",
  review: "Review",
  vendors: "Vendors",
  exports: "Exports",
  insights: "Insights",
  settings: "Settings",
  notfound: "Not found",
};

/**
 * The frame around every screen: the name, the places you can go, notices that must always be
 * visible (hosted mode, no reader, lost contact) and the demo-data label.
 */
export default function Shell({ children }: { children: ReactNode }) {
  const route = useRoute();
  const { load, reload, last } = useApi("status", (signal) => api.status(signal), {
    poll: true,
    pollMs: 15_000,
  });
  const main = useRef<HTMLElement>(null);
  const first = useRef(true);

  useEffect(() => {
    document.title = `${TITLE[route.name]} – Citetally`;
    if (first.current) {
      first.current = false;
      return;
    }
    main.current?.focus(); // after moving to another screen, keyboard and screen reader users start at its top
  }, [route.name]);

  const status = last;
  const active = section(route);

  return (
    <>
      <a className="skip" href="#main" onClick={() => main.current?.focus()}>
        Skip to the content
      </a>
      {status?.hosted_mode && (
        <Banner tone="warn">Hosted model mode: page content is sent to the hosted provider.</Banner>
      )}
      {status && status.ocr_available === false && (
        <Banner tone="warn">
          The text reader (Tesseract) was not found, so scans and photos cannot be read yet. PDFs
          with selectable text still work.
        </Banner>
      )}
      {load.kind === "error" && status && (
        <Banner tone="block">
          Lost contact with Citetally. What you see may be out of date. Trying again every few
          seconds.
        </Banner>
      )}
      <header className="masthead">
        <a className="brand" href={hrefFor({ name: "inbox" })}>
          Citetally
        </a>
        <nav aria-label="Main">
          <ul>
            {NAV.map(({ route: target, label }) => (
              <li key={target.name}>
                <a
                  href={hrefFor(target)}
                  aria-current={active === target.name ? "page" : undefined}
                >
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" ref={main} tabIndex={-1}>
        {!status && load.kind === "loading" && <Skeleton rows={3} label="Connecting" />}
        {!status && load.kind === "error" && (
          <EmptyState
            role="alert"
            title={load.error.code === UNREACHABLE ? "Cannot reach Citetally" : "Citetally is not answering"}
            actions={
              <button type="button" className="button" onClick={reload}>
                Try again
              </button>
            }
          >
            {errorAdvice(load.error)}
          </EmptyState>
        )}
        {status && children}
      </main>
      {status?.synthetic_data && (
        <footer className="demo-footer">
          Demo data. All vendors, invoices and amounts are invented.
        </footer>
      )}
    </>
  );
}

function errorAdvice(error: ApiError): string {
  const base =
    error.code === UNREACHABLE
      ? "The app could not reach its local service. Start it with: python -m citetally"
      : error.message;
  return error.requestId ? `${base} (request ${error.requestId})` : base;
}
