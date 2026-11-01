import { useMemo, useState, type ReactNode } from "react";

import { api, type InsightsOut } from "../api/client";
import { CHECK_TITLE } from "../lib/copy";
import { formatMinor } from "../lib/money";
import { duration, periodRange, type Period } from "../lib/time";
import { useApi } from "../lib/useApi";
import { labelFor } from "../review/fields";
import BarList, { type BarRow } from "../ui/BarList";
import EmptyState from "../ui/EmptyState";
import Skeleton from "../ui/Skeleton";

const PERIODS: { value: Period; label: string }[] = [
  { value: "month", label: "This month" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "year", label: "This year" },
  { value: "all", label: "All time" },
];

const AGE_LABEL: Record<InsightsOut["waiting_by_age"][number]["bucket"], string> = {
  under_1_day: "Less than a day",
  "1_to_3_days": "1 to 3 days",
  "3_to_7_days": "3 to 7 days",
  over_7_days: "More than 7 days",
};

type Spend = InsightsOut["by_vendor"][number];

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="insight">
      <h2>{title}</h2>
      {note && <p className="quiet">{note}</p>}
      {children}
    </section>
  );
}

/** Amounts in different currencies are never added, so each currency gets its own list. */
function Spending({ rows, what }: { rows: readonly Spend[]; what: string }) {
  const groups = useMemo(() => {
    const byCurrency = new Map<string, Spend[]>();
    for (const row of rows) byCurrency.set(row.currency, [...(byCurrency.get(row.currency) ?? []), row]);
    return [...byCurrency.entries()];
  }, [rows]);

  if (groups.length === 0) {
    return <p className="quiet">Nothing has been approved in this period yet.</p>;
  }
  return (
    <>
      {groups.map(([currency, list]) => {
        const total = list.reduce((sum, row) => sum + row.total_minor, 0);
        const bars: BarRow[] = list.map((row) => ({
          key: `${row.code ?? row.label}`,
          label: row.label,
          value: row.total_minor,
          text: formatMinor(row.total_minor, currency),
          note: `(${plural(row.entries, "entry", "entries")})`,
        }));
        return (
          <div key={currency} className="currency-group">
            {groups.length > 1 && <h3>{currency}</h3>}
            <p className="quiet">
              {plural(
                list.reduce((sum, row) => sum + row.entries, 0),
                "entry",
                "entries",
              )}{" "}
              in all, {formatMinor(total, currency)}. Credit notes are taken off.
            </p>
            <BarList
              title={`Spending by ${what}${groups.length > 1 ? ` in ${currency}` : ""}`}
              rows={bars}
              headers={[what[0].toUpperCase() + what.slice(1), "Entries", "Total"]}
              cells={(row) => {
                const source = list.find((s) => (s.code ?? s.label) === row.key);
                return [row.label, String(source?.entries ?? ""), row.text];
              }}
              empty="Nothing has been approved in this period yet."
              limit={10}
            />
          </div>
        );
      })}
    </>
  );
}

export default function Insights() {
  const [period, setPeriod] = useState<Period>("all");
  const range = periodRange(period);
  const key = `${range.from ?? ""}:${range.to ?? ""}`;
  const insights = useApi(key, (signal) => api.insights(range.from, range.to, signal));
  const data = insights.load.kind === "ready" ? insights.load.data : null;

  const waiting = data?.waiting_by_age ?? [];
  const waitingTotal = waiting.reduce((sum, bucket) => sum + bucket.documents, 0);
  const percent = data && data.approved_documents > 0 ? Math.round((100 * data.edited_documents) / data.approved_documents) : 0;

  return (
    <>
      <h1>Insights</h1>
      <p className="lead">
        Counts and sums of what you have reviewed. Nothing here is a forecast or a score.
      </p>

      <div className="chips" role="group" aria-label="Period">
        {PERIODS.map((p) => (
          <button
            key={p.value}
            type="button"
            className="filter-chip"
            aria-pressed={p.value === period}
            onClick={() => setPeriod(p.value)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {insights.load.kind === "loading" && <Skeleton rows={6} label="Loading insights" />}

      {insights.load.kind === "error" && (
        <EmptyState
          role="alert"
          title="The insights could not be loaded"
          actions={
            <button type="button" className="button" onClick={insights.reload}>
              Try again
            </button>
          }
        >
          {insights.load.error.message}
          {insights.load.error.requestId ? ` (request ${insights.load.error.requestId})` : ""}
        </EmptyState>
      )}

      {data && (
        <div className="insights-grid">
          <Section title="Spending by category" note="Approved and exported entries, by the date printed on the document.">
            <Spending rows={data.by_category} what="category" />
          </Section>

          <Section title="Spending by vendor">
            <Spending rows={data.by_vendor} what="vendor" />
          </Section>

          <Section title="Waiting for review" note="How long documents have been in the list. This is today's list, whatever period is chosen.">
            {waitingTotal === 0 ? (
              <p className="quiet">Nothing is waiting.</p>
            ) : (
              <BarList
                title="Documents waiting, by age"
                rows={waiting.map((b) => ({
                  key: b.bucket,
                  label: AGE_LABEL[b.bucket],
                  value: b.documents,
                  text: plural(b.documents, "document", "documents"),
                }))}
                headers={["Waiting", "Documents"]}
                cells={(row) => [row.label, String(row.value)]}
                empty="Nothing is waiting."
              />
            )}
          </Section>

          <Section title="How much needed fixing" note="Approved in this period.">
            {data.approved_documents === 0 ? (
              <p className="quiet">Nothing has been approved in this period yet.</p>
            ) : (
              <>
                <p className="headline">
                  {data.edited_documents} of {plural(data.approved_documents, "approved document", "approved documents")} needed a value
                  changed by hand ({percent}%).
                </p>
                <BarList
                  title="Fields changed by hand"
                  rows={data.edited_fields.map((f) => ({
                    key: f.field,
                    label: labelFor(f.field),
                    value: f.edits,
                    text: plural(f.edits, "change", "changes"),
                  }))}
                  headers={["Field", "Changes"]}
                  cells={(row) => [row.label, String(row.value)]}
                  empty="No value was changed by hand."
                />
              </>
            )}
          </Section>

          <Section title="Checks that fire most" note="Documents added in this period that have the check failing now.">
            <BarList
              title="Checks failing, by how many documents"
              rows={data.checks_failing.map((c) => ({
                key: c.check_code,
                label: CHECK_TITLE[c.check_code],
                value: c.documents,
                text: plural(c.documents, "document", "documents"),
                note: c.overridden > 0 ? `(${c.overridden} accepted with a reason)` : undefined,
              }))}
              headers={["Check", "Documents", "Accepted with a reason"]}
              cells={(row) => {
                const source = data.checks_failing.find((c) => c.check_code === row.key);
                return [row.label, String(row.value), String(source?.overridden ?? 0)];
              }}
              empty="No check is failing."
            />
          </Section>

          <Section title="Review time">
            {data.review_seconds_median === null ? (
              <p className="quiet">No review time has been recorded in this period yet.</p>
            ) : (
              <>
                <p className="headline">
                  Median: {duration(data.review_seconds_median)}
                </p>
                <p className="quiet">
                  From {plural(data.review_seconds_count, "decision", "decisions")} (approvals and rejections) where the
                  Review screen recorded how long it was open.
                </p>
              </>
            )}
          </Section>
        </div>
      )}
    </>
  );
}
