import { useEffect, useState } from "react";

import { api, type DocumentSummary } from "../api/client";
import { shortDate } from "../lib/time";
import { useApi } from "../lib/useApi";
import Dialog from "../ui/Dialog";
import Money from "../ui/Money";

function Facts({ row, title }: { row: DocumentSummary; title: string }) {
  return (
    <div className="compare-col">
      <h3>{title}</h3>
      <dl>
        <dt>File</dt>
        <dd className="clip-wrap">{row.original_filename}</dd>
        <dt>Vendor</dt>
        <dd className="clip-wrap">{row.vendor_name ?? "Unknown vendor"}</dd>
        <dt>Invoice number</dt>
        <dd className="clip-wrap">{row.invoice_number ?? "–"}</dd>
        <dt>Date</dt>
        <dd>{shortDate(row.entry_date) || "–"}</dd>
        <dt>Total</dt>
        <dd>
          <Money minor={row.total_minor} currency={row.currency} credit={row.entry_type === "credit_note"} />
        </dd>
      </dl>
    </div>
  );
}

/** Find the other document, see both side by side, then confirm. */
export default function DuplicateDialog({
  current,
  onConfirm,
  onClose,
}: {
  current: DocumentSummary;
  onConfirm: (originalId: number) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<DocumentSummary | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(text), 300);
    return () => window.clearTimeout(timer);
  }, [text]);

  const found = useApi(`dups:${query}`, (signal) => api.documents({ q: query, limit: 20 }, signal));
  const rows =
    found.load.kind === "ready" ? found.load.data.items.filter((r) => r.id !== current.id && r.status !== "duplicate") : [];

  return (
    <Dialog title="Mark as a duplicate of…" onClose={onClose} wide>
      {!chosen ? (
        <>
          <label className="field field-wide">
            <span>Find the other document by vendor, invoice number or file name</span>
            <input type="search" value={text} onChange={(event) => setText(event.target.value)} maxLength={100} />
          </label>
          <ul className="picker-list" aria-label="Documents found">
            {found.load.kind === "ready" && rows.length === 0 && <li className="quiet">No other document matches.</li>}
            {rows.map((r) => (
              <li key={r.id}>
                <button type="button" className="button" onClick={() => setChosen(r)}>
                  {r.original_filename} · {r.vendor_name ?? "Unknown vendor"} · {r.invoice_number ?? "no number"}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <div className="compare">
            <Facts row={current} title="This document" />
            <Facts row={chosen} title="The other document" />
          </div>
          <p className="quiet">
            This document will be set aside as a duplicate of the other one. It will not be exported.
            This will be recorded.
          </p>
        </>
      )}
      <div className="dialog-actions">
        {chosen && (
          <button type="button" className="button" onClick={() => setChosen(null)}>
            Choose another
          </button>
        )}
        <button type="button" className="button" onClick={onClose}>
          Cancel
        </button>
        {chosen && (
          <button type="button" className="button button-primary" onClick={() => onConfirm(chosen.id)}>
            Mark as duplicate
          </button>
        )}
      </div>
    </Dialog>
  );
}
