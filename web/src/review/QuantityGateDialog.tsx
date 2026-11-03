import { useState } from "react";

import type { EntryLine } from "../api/client";
import Dialog from "../ui/Dialog";

/**
 * Shown before approving when some lines have no quantity. Nothing flags them, and a quantity the
 * reading dropped looks the same as a page that prints none. The reviewer is asked to look at the
 * page and say which it is. The answer is not stored: it only slows the approval down on purpose.
 */
export default function QuantityGateDialog({
  lines,
  onApprove,
  onBack,
}: {
  lines: readonly EntryLine[];
  onApprove: () => void;
  onBack: () => void;
}) {
  const [ticked, setTicked] = useState(false);
  return (
    <Dialog title="Lines with no quantity" onClose={onBack}>
      <div className="dialog-intro">
        <p>
          {lines.length === 1 ? "This line has" : `These ${lines.length} lines have`} no quantity. Nothing checks{" "}
          {lines.length === 1 ? "it" : "them"}, and the reading sometimes drops a quantity the page prints. Look at the
          page before approving.
        </p>
        <ul className="unlocated">
          {lines.map((line) => (
            <li key={line.id}>
              <strong>Line {line.line_number}</strong>
              {line.description ? `: ${line.description}` : ""}
            </li>
          ))}
        </ul>
      </div>
      <label className="check-confirm">
        <input type="checkbox" checked={ticked} onChange={(event) => setTicked(event.target.checked)} />
        <span>
          I looked at the page. {lines.length === 1 ? "This line prints" : "These lines print"} no quantity, or I
          entered {lines.length === 1 ? "it" : "them"}.
        </span>
      </label>
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onBack}>
          Go back
        </button>
        <button type="button" className="button button-primary" disabled={!ticked} onClick={onApprove}>
          Approve anyway
        </button>
      </div>
    </Dialog>
  );
}
