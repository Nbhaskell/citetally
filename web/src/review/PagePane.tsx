import { useEffect, useMemo, useRef, useState } from "react";

import type { EntryOut, Evidence, PageOut } from "../api/client";
import Icon from "../ui/Icon";
import { evidenceKey, labelFor, type FieldKey } from "./fields";

type Zoom = "fit" | "actual" | number;

/**
 * The page, with a box over each value that was found on it. Click a box to go to its field.
 * Everything the boxes show is also a list underneath, so nobody depends on the picture.
 */
export default function PagePane({
  pages,
  evidence,
  entry,
  activeKey,
  onPick,
}: {
  pages: readonly PageOut[];
  evidence: readonly Evidence[];
  entry: EntryOut | null;
  activeKey: FieldKey | null;
  onPick: (key: FieldKey) => void;
}) {
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState<Zoom>("fit");
  const [seen, setSeen] = useState<FieldKey | null>(null);
  const sheet = useRef<HTMLDivElement>(null);

  // When another value comes into focus, show the page it is on.
  if (seen !== activeKey) {
    setSeen(activeKey);
    const target = evidence.find((e) => e.found && evidenceKey(e) === activeKey);
    if (target?.page_number && target.page_number !== pageNumber) setPageNumber(target.page_number);
  }
  const page = pages.find((p) => p.page_number === pageNumber) ?? pages[0];

  // ...and bring its box into view inside the scrolling picture.
  useEffect(() => {
    if (!activeKey) return;
    const escaped = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(activeKey) : activeKey;
    sheet.current
      ?.querySelector<HTMLElement>(`[data-key="${escaped}"]`)
      ?.scrollIntoView?.({ block: "center", inline: "center" });
  }, [activeKey, pageNumber]);

  const lineNumbers = useMemo(
    () => new Map((entry?.lines ?? []).map((line) => [line.id, line.line_number])),
    [entry],
  );
  const onThisPage = evidence.filter(
    (e) => e.found && e.x0 !== null && e.page_number === page?.page_number,
  );

  if (!page) {
    return (
      <section className="page-pane" aria-label="The page">
        <p className="quiet">The pages of this document are not ready yet.</p>
      </section>
    );
  }

  const width = zoom === "fit" ? "100%" : zoom === "actual" ? `${page.width_px}px` : `${zoom * 100}%`;
  const step = (delta: number) => {
    const now = typeof zoom === "number" ? zoom : 1;
    setZoom(Math.min(4, Math.max(0.5, Math.round((now + delta) * 100) / 100)));
  };

  return (
    <section className="page-pane" aria-label="The page">
      <div className="page-tools" role="group" aria-label="Page view">
        {pages.length > 1 && (
          <>
            <button
              type="button"
              className="button button-small"
              disabled={page.page_number === 1}
              onClick={() => setPageNumber(page.page_number - 1)}
            >
              Previous page
            </button>
            <span aria-live="polite">
              Page {page.page_number} of {pages.length}
            </span>
            <button
              type="button"
              className="button button-small"
              disabled={page.page_number === pages.length}
              onClick={() => setPageNumber(page.page_number + 1)}
            >
              Next page
            </button>
          </>
        )}
        <button type="button" className="button button-small" aria-pressed={zoom === "fit"} onClick={() => setZoom("fit")}>
          Fit width
        </button>
        <button type="button" className="button button-small" aria-pressed={zoom === "actual"} onClick={() => setZoom("actual")}>
          Actual size
        </button>
        <button type="button" className="button button-small" aria-label="Zoom out" onClick={() => step(-0.25)}>
          −
        </button>
        <button type="button" className="button button-small" aria-label="Zoom in" onClick={() => step(0.25)}>
          +
        </button>
      </div>

      <div className="page-scroll" tabIndex={0} role="region" aria-label="Page picture, scrollable">
        <div className="page-sheet" style={{ width }} ref={sheet}>
          <img
            src={page.image_url}
            alt={`Page ${page.page_number} of the document`}
            width={page.width_px}
            height={page.height_px}
          />
          <div className="boxes" aria-hidden="true">
            {onThisPage.map((e) => {
              const key = evidenceKey(e);
              return (
                <div
                  key={e.id}
                  className={`box${key === activeKey ? " box-active" : ""}`}
                  data-key={key}
                  style={{
                    left: `${(e.x0 ?? 0) * 100}%`,
                    top: `${(e.y0 ?? 0) * 100}%`,
                    width: `${((e.x1 ?? 0) - (e.x0 ?? 0)) * 100}%`,
                    height: `${((e.y1 ?? 0) - (e.y0 ?? 0)) * 100}%`,
                  }}
                  onClick={() => onPick(key)}
                />
              );
            })}
          </div>
        </div>
      </div>

      {evidence.length > 0 && (
        <ul className="evidence-list" aria-label="Where each value was found">
          {evidence.map((e) => {
            const key = evidenceKey(e);
            const label = labelFor(e.field, e.line_id === null ? null : (lineNumbers.get(e.line_id) ?? null));
            return (
              <li key={e.id} className={e.found ? "" : "evidence-missing"}>
                <button
                  type="button"
                  className="link-button"
                  aria-current={key === activeKey ? "true" : undefined}
                  onClick={() => onPick(key)}
                >
                  {e.found ? <Icon name="check" size={13} /> : <Icon name="alert" size={13} />}
                  <span className="evidence-label">{label}</span>
                  <span className="quiet">
                    {e.found ? `found on page ${e.page_number}` : "not found on the page"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <details className="text-read">
        <summary>Text as read</summary>
        <pre>{page.text}</pre>
      </details>
    </section>
  );
}
