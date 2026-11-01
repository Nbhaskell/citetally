import { useState } from "react";

import { api, ApiError, type ExportCreated, type ExportProfile } from "../api/client";
import { formatDecimal } from "../lib/money";
import { shortDate } from "../lib/time";
import { useApi } from "../lib/useApi";
import Dialog from "../ui/Dialog";
import EmptyState from "../ui/EmptyState";
import Icon from "../ui/Icon";
import Link from "../ui/Link";
import Skeleton from "../ui/Skeleton";
import { useToast } from "../ui/Toast";

const PROFILES: { value: ExportProfile; label: string; help: string }[] = [
  { value: "entries_csv", label: "One row per entry", help: "Each invoice, receipt or credit note is one row with its totals." },
  { value: "lines_csv", label: "One row per line item", help: "Each line on a document is one row, with the entry's details repeated." },
];

const PROFILE_LABEL: Record<ExportProfile, string> = {
  entries_csv: "One row per entry",
  lines_csv: "One row per line item",
};

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function describe(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

function when(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function range(first: string | null, last: string | null): string {
  if (!first || !last) return "";
  return first === last ? shortDate(first) : `${shortDate(first)} to ${shortDate(last)}`;
}

export default function Exports() {
  const toast = useToast();
  const [profile, setProfile] = useState<ExportProfile>("entries_csv");
  const [again, setAgain] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [made, setMade] = useState<ExportCreated | null>(null);

  const preview = useApi(`${profile}:${again}`, (signal) => api.exportPreview(profile, again, signal));
  const history = useApi("exports", (signal) => api.exports(signal));
  const ready = preview.load.kind === "ready" ? preview.load.data : null;
  const currencies = ready ? Object.entries(ready.totals) : [];

  async function create() {
    setBusy(true);
    setProblem(null);
    try {
      const created = await api.createExport(profile, again);
      setMade(created);
      setConfirming(false);
      toast.show(`Export ready: ${plural(created.export.entry_count, "entry", "entries")}.`);
      preview.reload();
      history.reload();
    } catch (error) {
      setConfirming(false);
      setProblem(describe(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Exports</h1>
      <p className="lead">
        An export makes a CSV file you download and import into your accounting software yourself.
        Citetally never sends anything anywhere.
      </p>

      <fieldset className="profiles">
        <legend>What should each row be?</legend>
        {PROFILES.map((p) => (
          <label key={p.value} className="profile">
            <input
              type="radio"
              name="profile"
              value={p.value}
              checked={profile === p.value}
              onChange={() => setProfile(p.value)}
            />
            <span>
              <strong>{p.label}</strong>
              <span className="quiet">{p.help}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <label className="check-option">
        <input type="checkbox" checked={again} onChange={(event) => setAgain(event.target.checked)} />
        <span>Include entries I've already exported</span>
      </label>
      {again && (
        <p className="notice notice-warn" role="status">
          <Icon name="alert" /> These may already be in your accounting software. Importing them again
          can create duplicates.
        </p>
      )}

      {problem && (
        <p className="notice notice-block" role="alert">
          <Icon name="alert" /> {problem}
        </p>
      )}

      {made && (
        <section className="export-made" aria-label="The file you just made">
          <h2>
            <Icon name="check" /> Your file is ready
          </h2>
          <p>
            {plural(made.export.entry_count, "entry", "entries")}, {plural(made.export.row_count, "row", "rows")}.
            {made.skipped_already_exported > 0 &&
              ` ${plural(made.skipped_already_exported, "entry was", "entries were")} left out because ${made.skipped_already_exported === 1 ? "it was" : "they were"} already exported.`}
          </p>
          <a className="button button-primary" href={made.export.download_url} download={made.export.file_name}>
            Download {made.export.file_name}
          </a>
          <p className="quiet">The entries are now marked Exported. Import the file into your accounting software yourself.</p>
        </section>
      )}

      {preview.load.kind === "loading" && <Skeleton rows={3} label="Checking what is ready" />}

      {preview.load.kind === "error" && (
        <EmptyState
          role="alert"
          title="We couldn't check what is ready"
          actions={
            <button type="button" className="button" onClick={preview.reload}>
              Try again
            </button>
          }
        >
          {preview.load.error.message}
          {preview.load.error.requestId ? ` (request ${preview.load.error.requestId})` : ""}
        </EmptyState>
      )}

      {ready && ready.entry_count === 0 && (
        <EmptyState
          title="Nothing is ready to export"
          actions={
            <Link to={{ name: "inbox" }} className="button">
              Go to the Inbox
            </Link>
          }
        >
          {ready.skipped_already_exported > 0
            ? `${plural(ready.skipped_already_exported, "approved entry has", "approved entries have")} already been exported. Tick the box above to include ${ready.skipped_already_exported === 1 ? "it" : "them"} again.`
            : "Approve entries in the Inbox and they will be ready here."}
        </EmptyState>
      )}

      {ready && ready.entry_count > 0 && (
        <section className="export-ready" aria-label="Ready to export">
          <h2>
            Ready to export: {plural(ready.entry_count, "approved entry", "approved entries")}
          </h2>
          <dl className="facts">
            {currencies.length > 0 && (
              <div>
                <dt>Total</dt>
                <dd>{currencies.map(([currency, total]) => formatDecimal(total, currency)).join(" and ")}</dd>
              </div>
            )}
            {range(ready.first_date, ready.last_date) && (
              <div>
                <dt>Dates</dt>
                <dd>{range(ready.first_date, ready.last_date)}</dd>
              </div>
            )}
            <div>
              <dt>Rows in the file</dt>
              <dd>{ready.row_count}</dd>
            </div>
            {ready.skipped_already_exported > 0 && (
              <div>
                <dt>Left out</dt>
                <dd>{plural(ready.skipped_already_exported, "entry", "entries")} already exported</dd>
              </div>
            )}
          </dl>

          <h3>The first rows</h3>
          <div className="table-wrap">
            <table className="sample">
              <caption className="sr-only">The first rows of the file</caption>
              <thead>
                <tr>
                  {ready.columns.map((column) => (
                    <th key={column} scope="col">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ready.sample.map((row, index) => (
                  <tr key={index}>
                    {row.map((cell, column) => (
                      <td key={column}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button type="button" className="button button-primary" onClick={() => setConfirming(true)}>
            Export approved entries
          </button>
        </section>
      )}

      <h2 className="section-head">Earlier exports</h2>
      {history.load.kind === "loading" && <Skeleton rows={2} label="Loading earlier exports" />}
      {history.load.kind === "error" && (
        <EmptyState
          role="alert"
          title="Earlier exports could not be loaded"
          actions={
            <button type="button" className="button" onClick={history.reload}>
              Try again
            </button>
          }
        >
          {history.load.error.message}
        </EmptyState>
      )}
      {history.load.kind === "ready" && history.load.data.length === 0 && (
        <p className="quiet">No exports yet. Files you make will be listed here so you can download them again.</p>
      )}
      {history.load.kind === "ready" && history.load.data.length > 0 && (
        <div className="table-wrap">
          <table className="queue history">
            <caption className="sr-only">Earlier exports</caption>
            <thead>
              <tr>
                <th scope="col">Made</th>
                <th scope="col">Rows are</th>
                <th scope="col" className="num">
                  Entries
                </th>
                <th scope="col">File</th>
                <th scope="col">Fingerprint</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {history.load.data.map((item) => (
                <tr key={item.id}>
                  <th scope="row" data-label="Made">
                    {when(item.created_at)}
                  </th>
                  <td data-label="Rows are">{PROFILE_LABEL[item.profile]}</td>
                  <td data-label="Entries" className="num">
                    {item.entry_count}
                  </td>
                  <td data-label="File">{item.file_name}</td>
                  <td data-label="Fingerprint" title={item.file_sha256}>
                    <code>{item.file_sha256.slice(0, 12)}</code>
                  </td>
                  <td data-label="Actions" className="actions">
                    <a className="button button-small" href={item.download_url} download={item.file_name}>
                      Download again
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirming && ready && (
        <Dialog title="Export these entries?" onClose={() => setConfirming(false)}>
          <p className="dialog-intro">
            {plural(ready.entry_count, "entry", "entries")} will be written to a CSV file and marked
            Exported. Nothing is sent anywhere. You download the file and import it yourself.
          </p>
          {again && (
            <p className="notice notice-warn">
              <Icon name="alert" /> This includes entries you've already exported.
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="button" onClick={() => setConfirming(false)}>
              Cancel
            </button>
            <button type="button" className="button button-primary" disabled={busy} onClick={create}>
              Export {plural(ready.entry_count, "entry", "entries")}
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
