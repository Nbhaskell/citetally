import { useState } from "react";

import type { CheckOut, DocumentDetail } from "../api/client";
import { CHECK_TITLE } from "../lib/copy";
import { formatMinor } from "../lib/money";
import Dialog from "../ui/Dialog";
import { FIELD_LABEL } from "./fields";

/** Read the page again, or ask the model again. Both replace what was made from the page. */
export function ReprocessDialog({
  onConfirm,
  onClose,
}: {
  onConfirm: (from: "read" | "extract") => void;
  onClose: () => void;
}) {
  const [from, setFrom] = useState<"read" | "extract">("extract");
  return (
    <Dialog title="Reprocess this document" onClose={onClose}>
      <fieldset className="choice">
        <legend className="sr-only">Where to start again</legend>
        <label>
          <input type="radio" name="from" checked={from === "extract"} onChange={() => setFrom("extract")} />
          <span>
            <strong>Ask the model again</strong>
            <br />
            Keeps the page as read and finds the values again.
          </span>
        </label>
        <label>
          <input type="radio" name="from" checked={from === "read"} onChange={() => setFrom("read")} />
          <span>
            <strong>Read the page again</strong>
            <br />
            Starts from the file. Use this if the page was read badly.
          </span>
        </label>
      </fieldset>
      <p className="quiet">
        Values you changed on this document will be replaced by the new reading, and checks start
        over. The old edits stay in the history.
      </p>
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onClose}>
          Cancel
        </button>
        <button type="button" className="button button-primary" onClick={() => onConfirm(from)}>
          Reprocess
        </button>
      </div>
    </Dialog>
  );
}

const MONEY_FIELDS = new Set(["subtotal", "tax_total", "shipping", "discount", "total", "amount"]);

const STAGE_WORDS: Record<string, string> = {
  ingest: "File accepted",
  read: "Page read",
  extract: "Values found",
  ground: "Values located on the page",
  match: "Vendor and category matched",
  check: "Checks run",
};

interface Item {
  at: string;
  text: string;
}

export function timeline(detail: DocumentDetail): Item[] {
  const cur = detail.entry?.currency ?? "USD";
  const items: Item[] = [];
  for (const e of detail.history) {
    if (e.event_type === "stage_finished" && e.stage) {
      const secs = e.duration_ms ? ` (${(e.duration_ms / 1000).toFixed(1)} s)` : "";
      items.push({ at: e.created_at, text: `${STAGE_WORDS[e.stage] ?? e.stage}${secs}` });
    } else if (e.event_type === "stage_failed" && e.stage) {
      items.push({ at: e.created_at, text: `${STAGE_WORDS[e.stage] ?? e.stage} failed` });
    } else if (e.event_type === "status_changed" && e.to_status) {
      items.push({ at: e.created_at, text: `Status: ${e.from_status ?? "new"} → ${e.to_status}`.replace(/_/g, " ") });
    } else if (e.event_type === "check_failed" && typeof e.payload.check === "string") {
      items.push({ at: e.created_at, text: `Check failed: ${CHECK_TITLE[e.payload.check as CheckOut["check_code"]] ?? e.payload.check}` });
    } else if (e.event_type === "export_created") {
      items.push({ at: e.created_at, text: "Included in an export" });
    }
  }
  const show = (field: string, value: string | null) =>
    value === null ? "empty" : MONEY_FIELDS.has(field) ? formatMinor(Number(value), cur) : value;
  for (const edit of detail.edits) {
    items.push({
      at: edit.created_at,
      text: `You changed ${(FIELD_LABEL[edit.field] ?? edit.field).toLowerCase()}: ${show(edit.field, edit.old_value)} → ${show(edit.field, edit.new_value)}`,
    });
  }
  for (const r of detail.reviews) {
    const words: Record<string, string> = { approve: "Approved", reject: "Rejected", reopen: "Reopened", mark_duplicate: "Marked as a duplicate" };
    const extra = [r.reason ? `“${r.reason}”` : "", r.overrides ? `${r.overrides} accepted with a reason` : "", r.review_seconds !== null ? `${r.review_seconds} s` : ""]
      .filter(Boolean)
      .join(", ");
    items.push({ at: r.created_at, text: `${words[r.decision] ?? r.decision}${extra ? ` (${extra})` : ""}` });
  }
  return items.sort((a, b) => a.at.localeCompare(b.at));
}

/** Everything that happened to this document, in order, in words. No page text. */
export function HistoryDialog({ detail, onClose }: { detail: DocumentDetail; onClose: () => void }) {
  const items = timeline(detail);
  return (
    <Dialog title="History" onClose={onClose} side>
      <ol className="history">
        {items.map((item, i) => (
          <li key={i}>
            <time dateTime={item.at}>{new Date(item.at).toLocaleString()}</time>
            <span>{item.text}</span>
          </li>
        ))}
      </ol>
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onClose}>
          Close
        </button>
      </div>
    </Dialog>
  );
}

const SHORTCUTS: [string, string][] = [
  ["j / k", "Next / previous document waiting for review"],
  ["a", "Approve (when nothing is left to resolve)"],
  ["r", "Reject…"],
  ["e", "Edit the first field"],
  ["g then p", "Move to the page picture"],
  ["?", "Show this list"],
];

export function ShortcutHelp({ onClose }: { onClose: () => void }) {
  return (
    <Dialog title="Keyboard shortcuts" onClose={onClose}>
      <dl className="shortcuts">
        {SHORTCUTS.map(([keys, what]) => (
          <div key={keys}>
            <dt>
              <kbd>{keys}</kbd>
            </dt>
            <dd>{what}</dd>
          </div>
        ))}
      </dl>
      <p className="quiet">Shortcuts do nothing while you are typing in a box.</p>
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onClose}>
          Close
        </button>
      </div>
    </Dialog>
  );
}
