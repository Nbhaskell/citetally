import { useState } from "react";

import { api, ApiError, type EntryOut } from "../api/client";
import { useApi } from "../lib/useApi";
import Dialog from "../ui/Dialog";
import Skeleton from "../ui/Skeleton";

function likeness(score: number): string {
  return score >= 0.9 ? "Probably the same" : "Possibly the same";
}

/**
 * Choose the vendor: one that is close to the printed name (suggested, never applied for you),
 * any existing one, or a new one made from the printed name.
 */
export default function VendorPicker({
  entry,
  onChoose,
  onClose,
}: {
  entry: EntryOut;
  onChoose: (choice: { vendor_id: number } | { create: true; name?: string }) => Promise<void>;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const vendors = useApi(`vendors:${entry.id}`, (signal) => api.vendors(signal));
  const suggestions = useApi(`suggest:${entry.id}`, (signal) => api.vendorSuggestions(entry.id, signal));

  async function choose(choice: { vendor_id: number } | { create: true; name?: string }) {
    setBusy(true);
    setProblem(null);
    try {
      await onChoose(choice);
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "Something went wrong.");
      setBusy(false);
    }
  }

  const all = vendors.load.kind === "ready" ? vendors.load.data : [];
  const shown = all.filter((v) => v.name.toLowerCase().includes(text.trim().toLowerCase()));
  const suggested = suggestions.load.kind === "ready" ? suggestions.load.data : [];
  const printed = entry.vendor_name_raw?.trim() ?? "";
  const searchName = text.trim();

  return (
    <Dialog title="Pick the vendor" onClose={onClose} wide>
      {printed && (
        <p>
          The page says: <strong>{printed}</strong>
        </p>
      )}
      {problem && (
        <p role="alert" className="notice notice-block">
          {problem}
        </p>
      )}

      {suggested.length > 0 && (
        <>
          <h3>Close to the printed name</h3>
          <ul className="picker-list">
            {suggested.map((s) => (
              <li key={s.vendor_id}>
                <button type="button" className="button" disabled={busy} onClick={() => choose({ vendor_id: s.vendor_id })}>
                  {likeness(s.score)}: {s.name}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      <label className="field field-wide">
        <span>Search your vendors</span>
        <input type="search" value={text} onChange={(event) => setText(event.target.value)} maxLength={100} />
      </label>
      {vendors.load.kind === "loading" && <Skeleton rows={3} label="Loading vendors" />}
      {vendors.load.kind === "ready" && (
        <ul className="picker-list" aria-label="Your vendors">
          {shown.length === 0 && <li className="quiet">No vendor has that name yet.</li>}
          {shown.map((v) => (
            <li key={v.id}>
              <button
                type="button"
                className="button"
                disabled={busy}
                aria-current={v.id === entry.vendor_id ? "true" : undefined}
                onClick={() => choose({ vendor_id: v.id })}
              >
                {v.name}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="picker-create">
        {printed && (
          <button type="button" className="button button-primary" disabled={busy} onClick={() => choose({ create: true })}>
            Create vendor “{printed}”
          </button>
        )}
        {searchName && searchName !== printed && !shown.some((v) => v.name.toLowerCase() === searchName.toLowerCase()) && (
          <button type="button" className="button" disabled={busy} onClick={() => choose({ create: true, name: searchName })}>
            Create vendor “{searchName}”
          </button>
        )}
      </div>
      <p className="quiet">
        The printed name is remembered as another name for the vendor you choose, so the next one is
        matched by itself.
      </p>
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onClose}>
          Cancel
        </button>
      </div>
    </Dialog>
  );
}
