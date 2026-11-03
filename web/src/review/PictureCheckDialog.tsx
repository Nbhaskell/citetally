import { useState } from "react";

import Dialog from "../ui/Dialog";
import { labelFor } from "./fields";
import type { Unlocated } from "./pictureCheck";

type Answer = "matches" | "differs";

/**
 * A confirmation for the values the page words could not place. Each value is answered on its own:
 * it matches the picture, or it does not. One tick for the lot let values through that nobody had
 * looked at, so the confirmation stays disabled until every value is marked as matching.
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
  const [answers, setAnswers] = useState<Record<number, Answer>>({});
  const everyoneMatches = values.every((_, i) => answers[i] === "matches");
  const anyDiffers = values.some((_, i) => answers[i] === "differs");
  const answeredCount = values.filter((_, i) => answers[i] !== undefined).length;
  return (
    <Dialog title="Check against the picture" onClose={onCancel}>
      <div className="dialog-intro">
        <p>
          The picture of the page was read for these {values.length === 1 ? "value" : `${values.length} values`}, but the
          text reading could not place {values.length === 1 ? "it" : "them"} on the page. Look at each one on the picture
          of the page and say whether it matches.
        </p>
      </div>
      <div className="picture-values">
        {values.map((value, i) => (
          <fieldset key={`${value.field}-${value.line ?? "h"}-${i}`} className="picture-value">
            <legend>
              <strong>{labelFor(value.field, value.line)}</strong>: {value.printed || "(empty)"}
            </legend>
            <label>
              <input
                type="radio"
                name={`picture-value-${i}`}
                checked={answers[i] === "matches"}
                onChange={() => setAnswers({ ...answers, [i]: "matches" })}
              />
              <span>Matches the picture</span>
            </label>
            <label>
              <input
                type="radio"
                name={`picture-value-${i}`}
                checked={answers[i] === "differs"}
                onChange={() => setAnswers({ ...answers, [i]: "differs" })}
              />
              <span>Not what the picture shows</span>
            </label>
          </fieldset>
        ))}
      </div>
      {anyDiffers && (
        <p className="notice notice-info" role="status">
          Close this and correct or clear it in the form. The value stays as the page prints it, or empty if the page
          prints nothing there.
        </p>
      )}
      <p className="quiet">
        {answeredCount} of {values.length} answered. This will be recorded with your approval.
      </p>
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="button button-primary" disabled={!everyoneMatches} onClick={onConfirm}>
          Confirm checked against the picture
        </button>
      </div>
    </Dialog>
  );
}
