import { useId } from "react";

import type { DocumentStatus } from "../api/client";

/**
 * The decisions, always in view. Approve stays visible when it cannot be used and says why, right
 * where the person is looking. Nothing here happens by itself.
 */
export default function ActionBar({
  status,
  unresolved,
  busy,
  onApprove,
  onReject,
  onDuplicate,
  onReprocess,
  onReopen,
  onHistory,
}: {
  status: DocumentStatus;
  unresolved: number;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onDuplicate: () => void;
  onReprocess: () => void;
  onReopen: () => void;
  onHistory: () => void;
}) {
  const reasonId = useId();
  const blocked = unresolved > 0;
  return (
    <div className="action-bar" role="toolbar" aria-label="Decisions">
      {status === "needs_review" && (
        <>
          <button
            type="button"
            className="button button-primary"
            disabled={busy || blocked}
            aria-describedby={blocked ? reasonId : undefined}
            onClick={onApprove}
          >
            Approve entry
          </button>
          {blocked && (
            <span id={reasonId} className="action-reason">
              {unresolved} {unresolved === 1 ? "check" : "checks"} must be resolved first
            </span>
          )}
          <button type="button" className="button" disabled={busy} onClick={onReject}>
            Reject…
          </button>
          <button type="button" className="button" disabled={busy} onClick={onDuplicate}>
            Mark as duplicate of…
          </button>
        </>
      )}
      {(status === "needs_review" || status === "failed" || status === "rejected") && (
        <button type="button" className="button" disabled={busy} onClick={onReprocess}>
          Reprocess…
        </button>
      )}
      {(status === "approved" || status === "rejected") && (
        <button type="button" className="button" disabled={busy} onClick={onReopen}>
          Reopen
        </button>
      )}
      {status === "exported" && (
        <span className="action-reason">Exported entries cannot be reopened. Correct it in your accounting software.</span>
      )}
      {status === "duplicate" && (
        <span className="action-reason">Set aside as a duplicate. It will not be exported.</span>
      )}
      <span className="action-spacer" />
      <button type="button" className="button" onClick={onHistory}>
        History
      </button>
    </div>
  );
}
