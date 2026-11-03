import { useState } from "react";

import Dialog from "../ui/Dialog";
import { labelFor } from "./fields";
import type { Unlocated } from "./pictureCheck";

/**
 * One deliberate confirmation for the values the page words could not place. The reviewer has to
 * look at the picture and tick the box; the decision is recorded with the approval.
 */
export default function PictureCheckDialog({
  values,
  onConfirm,
  onCancel,
}: {
  values: Unlocated[];
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [ticked, setTicked] = useState(false);
  return (
    <Dialog title="Check against the picture" onClose={onCancel}>
      <div className="dialog-intro">
        <p>
          The picture of the page was read for these {values.length === 1 ? "value" : `${values.length} values`}, but the
          text reading could not place {values.length === 1 ? "it" : "them"} on the page. Look at each one on the picture
          of the page.
        </p>
        <ul className="unlocated">
          {values.map((value, i) => (
            <li key={`${value.field}-${value.line ?? "h"}-${i}`}>
              <strong>{labelFor(value.field, value.line)}</strong>: {value.printed}
            </li>
          ))}
        </ul>
      </div>
      <label className="check-confirm">
        <input type="checkbox" checked={ticked} onChange={(event) => setTicked(event.target.checked)} />
        <span>
          I compared {values.length === 1 ? "this value" : "each of these values"} with the picture, and
          {values.length === 1 ? " it matches" : " they match"}.
        </span>
      </label>
      <p className="quiet">This will be recorded with your approval.</p>
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="button button-primary" disabled={!ticked} onClick={onConfirm}>
          Confirm checked against the picture
        </button>
      </div>
    </Dialog>
  );
}
