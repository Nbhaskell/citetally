import { useEffect, useMemo, useState } from "react";

import {
  api,
  ApiError,
  type CheckCode,
  type DocumentStatus,
  type DocumentSummary,
  type UploadResult,
} from "../api/client";
import { CHECK_TITLE, PROCESSING, PROCESSING_STEP, retryStage } from "../lib/copy";
import { age, secondsSince, shortDate } from "../lib/time";
import { useApi } from "../lib/useApi";
import CheckSummary from "../ui/CheckSummary";
import EmptyState from "../ui/EmptyState";
import Icon from "../ui/Icon";
import Link from "../ui/Link";
import Money from "../ui/Money";
import Skeleton from "../ui/Skeleton";
import StatusChip from "../ui/StatusChip";
import { useToast } from "../ui/Toast";
import UploadArea from "../ui/UploadArea";

interface Chip {
  key: string;
  label: string;
  /** Needs review also shows what is still being read, so a new upload appears at once. */
  statuses: DocumentStatus[];
  countOf: DocumentStatus;
}

const CHIPS: Chip[] = [
  { key: "needs_review", label: "Needs review", statuses: ["received", "read", "extracted", "needs_review"], countOf: "needs_review" },
  { key: "approved", label: "Approved", statuses: ["approved"], countOf: "approved" },
  { key: "rejected", label: "Rejected", statuses: ["rejected"], countOf: "rejected" },
  { key: "exported", label: "Exported", statuses: ["exported"], countOf: "exported" },
  { key: "failed", label: "Failed", statuses: ["failed"], countOf: "failed" },
  { key: "duplicate", label: "Duplicates", statuses: ["duplicate"], countOf: "duplicate" },
];

type Sort = "oldest" | "newest" | "blocking";
const PAGE = 50;
const POLL_MS = 3000;
const SLOW_SECONDS = 90;

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

function isProcessing(row: DocumentSummary): boolean {
  return PROCESSING.includes(row.status);
}

function vendorText(row: DocumentSummary): string {
  if (isProcessing(row) || row.status === "failed") return row.vendor_name ?? "";
  return row.vendor_name ?? "Unknown vendor";
}

function Progress({ row }: { row: DocumentSummary }) {
  const slow = secondsSince(row.updated_at) > SLOW_SECONDS;
  return (
    <div className="progress-note">
      <span className="progress" aria-hidden="true" />
      <span>{PROCESSING_STEP[row.status]}…</span>
      {slow && <span className="quiet"> Still working. The model is slow right now.</span>}
    </div>
  );
}

function Row({ row, onRetry }: { row: DocumentSummary; onRetry: (row: DocumentSummary) => void }) {
  const stage = row.status === "failed" ? retryStage(row.failure_stage) : null;
  const credit = row.entry_type === "credit_note";
  return (
    <tr>
      <th scope="row" data-label="File" className="cell-file">
        <Link to={{ name: "review", id: row.id }} className="file-link">
          <Icon name="file" />
          <span className="clip" title={row.original_filename}>
            {row.original_filename}
          </span>
        </Link>
        {row.status === "failed" && row.failure_message && (
          <p className="row-note">{row.failure_message}</p>
        )}
      </th>
      <td data-label="Vendor">
        <span className="clip" title={vendorText(row)}>
          {vendorText(row) || <span className="quiet">–</span>}
        </span>
      </td>
      <td data-label="Date">{shortDate(row.entry_date) || <span className="quiet">–</span>}</td>
      <td data-label="Total" className="num">
        <Money minor={row.total_minor} currency={row.currency} credit={credit} />
      </td>
      <td data-label="Checks">
        <CheckSummary row={row} />
      </td>
      <td data-label="Status">
        <StatusChip status={row.status} />
        {isProcessing(row) && <Progress row={row} />}
      </td>
      <td data-label="Age" className="quiet">
        {age(row.created_at)}
      </td>
      <td data-label="Actions" className="actions">
        <Link to={{ name: "review", id: row.id }} className="button button-small">
          {row.status === "needs_review" ? "Review" : "Open"}
        </Link>
        {stage && (
          <button type="button" className="button button-small" onClick={() => onRetry(row)}>
            <Icon name="retry" size={14} />
            Retry
          </button>
        )}
      </td>
    </tr>
  );
}

export default function Inbox() {
  const toast = useToast();
  const [chipKey, setChipKey] = useState("needs_review");
  const [text, setText] = useState("");
  const [check, setCheck] = useState<CheckCode | "">("");
  const [batch, setBatch] = useState("");
  const [sort, setSort] = useState<Sort>("oldest");
  const [uploading, setUploading] = useState(false);
  const [notices, setNotices] = useState<string[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [more, setMore] = useState<{ key: string; rows: DocumentSummary[]; cursor: string | null } | null>(null);

  const search = useDebounced(text, 300);
  const chip = CHIPS.find((c) => c.key === chipKey) ?? CHIPS[0];
  const order = sort === "newest" ? "newest" : "oldest";
  const key = JSON.stringify([chip.key, search.trim(), check, batch, order]);

  const counts = useApi("counts", (signal) => api.counts(signal));
  const list = useApi(
    key,
    (signal) =>
      api.documents(
        { statuses: chip.statuses, check, q: search, batch, order, limit: PAGE },
        signal,
      ),
    { poll: true, pollMs: POLL_MS },
  );

  const extra = more && more.key === key ? more : null;
  const loaded = list.load;
  const rows = useMemo(() => {
    const first = loaded.kind === "ready" ? loaded.data.items : [];
    const all = [...first, ...(extra?.rows ?? [])];
    if (sort !== "blocking") return all;
    return [...all].sort(
      (a, b) => (b.unresolved_checks?.length ?? 0) - (a.unresolved_checks?.length ?? 0) || a.id - b.id,
    );
  }, [loaded, extra, sort]);
  const nextCursor = extra ? extra.cursor : list.load.kind === "ready" ? list.load.data.next_cursor : null;
  const processing = rows.filter(isProcessing).length;
  const filtered = search.trim() !== "" || check !== "" || batch !== "";
  const countData = counts.load.kind === "ready" ? counts.load.data : null;
  const totalDocs = countData ? Object.values(countData.counts).reduce((a, b) => a + b, 0) : null;

  async function showMore() {
    if (!nextCursor) return;
    try {
      const page = await api.documents(
        { statuses: chip.statuses, check, q: search, batch, order, cursor: nextCursor, limit: PAGE },
      );
      setMore({ key, rows: [...(extra?.rows ?? []), ...page.items], cursor: page.next_cursor ?? null });
    } catch (error) {
      toast.show(error instanceof ApiError ? error.message : "Could not load more.");
    }
  }

  async function upload(files: File[]) {
    setUploading(true);
    setUploadError(null);
    setNotices([]);
    try {
      const label = `Upload ${new Date().toISOString().slice(0, 16).replace("T", " ")}`;
      await finishUpload(await api.upload(files, label));
    } catch (error) {
      setUploadError(describe(error));
    } finally {
      setUploading(false);
    }
  }

  async function loadDemo() {
    setUploading(true);
    setUploadError(null);
    try {
      await finishUpload(await api.loadDemo());
    } catch (error) {
      setUploadError(describe(error));
    } finally {
      setUploading(false);
    }
  }

  async function finishUpload(response: { results: UploadResult[] }) {
    const added = response.results.filter((r) => r.outcome === "accepted").length;
    const problems = response.results
      .filter((r) => r.outcome !== "accepted")
      .map((r) => `${r.filename}: ${r.message ?? (r.outcome === "duplicate" ? "Already in the list." : "Could not be added.")}`);
    setNotices(problems);
    if (added > 0) {
      toast.show(`${added} ${added === 1 ? "document" : "documents"} added. Reading ${added === 1 ? "it" : "them"} now.`);
      setChipKey("needs_review");
    }
    counts.reload();
    list.reload();
  }

  async function retry(row: DocumentSummary) {
    const stage = retryStage(row.failure_stage);
    if (!stage) return;
    try {
      await api.reprocess(row.id, stage);
      toast.show("Trying again.");
      counts.reload();
      list.reload();
    } catch (error) {
      toast.show(describe(error));
    }
  }

  function clearFilters() {
    setText("");
    setCheck("");
    setBatch("");
  }

  return (
    <>
      <h1>Inbox</h1>
      <UploadArea onFiles={upload} busy={uploading} />
      {uploadError && (
        <p className="notice notice-block" role="alert">
          <Icon name="alert" /> {uploadError}
        </p>
      )}
      {notices.length > 0 && (
        <ul className="notice notice-warn" aria-label="Files that were not added">
          {notices.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}

      <div className="chips" role="group" aria-label="Show documents that are">
        {CHIPS.map((c) => {
          const n = countData?.counts[c.countOf];
          return (
            <button
              key={c.key}
              type="button"
              className="filter-chip"
              aria-pressed={c.key === chip.key}
              aria-label={n === undefined ? c.label : `${c.label} ${n}`}
              onClick={() => setChipKey(c.key)}
            >
              {c.label}
              {n !== undefined && <span className="count">{n}</span>}
            </button>
          );
        })}
      </div>

      <div className="filters">
        <label className="field">
          <span>Search</span>
          <span className="search">
            <Icon name="search" />
            <input
              type="search"
              value={text}
              placeholder="Vendor, invoice number or file"
              onChange={(event) => setText(event.target.value)}
              maxLength={100}
            />
          </span>
        </label>
        <label className="field">
          <span>Problem</span>
          <select value={check} onChange={(event) => setCheck(event.target.value as CheckCode | "")}>
            <option value="">Any</option>
            {(Object.keys(CHECK_TITLE) as CheckCode[]).map((code) => (
              <option key={code} value={code}>
                {CHECK_TITLE[code]}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Batch</span>
          <select value={batch} onChange={(event) => setBatch(event.target.value)}>
            <option value="">All uploads</option>
            {(countData?.batches ?? []).map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Order</span>
          <select value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
            <option value="oldest">Oldest first</option>
            <option value="newest">Newest first</option>
            <option value="blocking">Blocking checks first</option>
          </select>
        </label>
      </div>

      {processing > 0 && (
        <p className="processing-note" role="status">
          {processing} still being read. This list updates by itself.
        </p>
      )}

      {list.load.kind === "loading" && <Skeleton rows={6} label="Loading documents" />}

      {list.load.kind === "error" && (
        <EmptyState
          role="alert"
          title="The list could not be loaded"
          actions={
            <button type="button" className="button" onClick={list.reload}>
              Try again
            </button>
          }
        >
          {list.load.error.message}
          {list.load.error.requestId ? ` (request ${list.load.error.requestId})` : ""}
        </EmptyState>
      )}

      {list.load.kind === "ready" && rows.length === 0 && (
        filtered ? (
          <EmptyState
            title="Nothing matches those filters"
            actions={
              <button type="button" className="button" onClick={clearFilters}>
                Clear the filters
              </button>
            }
          >
            Try a different search, or clear the filters to see everything in this list.
          </EmptyState>
        ) : totalDocs === 0 ? (
          <EmptyState
            title="Nothing here yet"
            actions={
              <button type="button" className="button button-primary" disabled={uploading} onClick={loadDemo}>
                Load demo documents
              </button>
            }
          >
            Drop in an invoice or receipt to begin. Or load the invented demo documents to try the
            app.
          </EmptyState>
        ) : (
          <EmptyState title={`No ${chip.label.toLowerCase()} documents`}>
            Nothing is in this list right now.
          </EmptyState>
        )
      )}

      {list.load.kind === "ready" && rows.length > 0 && (
        <>
          <p className="sr-only" role="status">
            {rows.length} {rows.length === 1 ? "document" : "documents"} shown
          </p>
          <div className="table-wrap">
          <table className="queue">
            <caption className="sr-only">Documents</caption>
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Vendor</th>
                <th scope="col">Date</th>
                <th scope="col" className="num">
                  Total
                </th>
                <th scope="col">Checks</th>
                <th scope="col">Status</th>
                <th scope="col">Age</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Row key={row.id} row={row} onRetry={retry} />
              ))}
            </tbody>
          </table>
          </div>
          {nextCursor && (
            <p className="more">
              <button type="button" className="button" onClick={showMore}>
                Show more
              </button>
            </p>
          )}
        </>
      )}
    </>
  );
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} (request ${error.requestId})` : error.message;
  }
  return "Something went wrong.";
}
