import type { DocumentSummary } from "../api/client";
import { CHECK_TITLE } from "../lib/copy";
import Icon from "./Icon";

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** "2 blocking, 1 warning", "All checks passed", or nothing to say before checks have run. */
export default function CheckSummary({
  row,
}: {
  row: Pick<DocumentSummary, "status" | "unresolved_checks" | "warnings">;
}) {
  if (row.status !== "needs_review") {
    return (
      <span className="quiet">
        <span aria-hidden="true">–</span>
        <span className="sr-only">No checks to show</span>
      </span>
    );
  }
  const blocking = row.unresolved_checks ?? [];
  const warnings = row.warnings ?? [];
  if (blocking.length === 0 && warnings.length === 0) {
    return (
      <span className="check-sum check-sum-ok">
        <Icon name="check" size={14} />
        All checks passed
      </span>
    );
  }
  const titles = [...blocking, ...warnings].map((code) => CHECK_TITLE[code]).join("; ");
  return (
    <span className="check-sum" title={titles}>
      {blocking.length > 0 && (
        <span className="check-sum-block">
          <Icon name="block" size={14} />
          {plural(blocking.length, "blocking", "blocking")}
        </span>
      )}
      {warnings.length > 0 && (
        <span className="check-sum-warn">
          <Icon name="alert" size={14} />
          {plural(warnings.length, "warning", "warnings")}
        </span>
      )}
      <span className="sr-only">: {titles}</span>
    </span>
  );
}
