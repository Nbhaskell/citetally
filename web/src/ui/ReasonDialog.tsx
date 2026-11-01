import { useId, useRef, useState, type ReactNode } from "react";

import Dialog from "./Dialog";

/**
 * Asks for a written reason before something that is recorded: accepting a failed check, or
 * rejecting a document. The confirm button stays off until the reason is long enough.
 */
export default function ReasonDialog({
  title,
  intro,
  label,
  placeholder,
  quick = [],
  minLength,
  confirmLabel,
  note = "This will be recorded.",
  onConfirm,
  onCancel,
}: {
  title: string;
  intro?: ReactNode;
  label: string;
  placeholder?: string;
  quick?: string[];
  minLength: number;
  confirmLabel: string;
  note?: string;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);
  const hintId = useId();
  const long = reason.trim().length >= minLength;

  return (
    <Dialog title={title} onClose={onCancel}>
      {intro && <div className="dialog-intro">{intro}</div>}
      {quick.length > 0 && (
        <div className="quick" role="group" aria-label="Quick reasons">
          {quick.map((choice) => (
            <button
              key={choice}
              type="button"
              className="filter-chip"
              aria-pressed={reason === choice}
              onClick={() => {
                if (choice === "Other") {
                  setReason("");
                  area.current?.focus();
                } else {
                  setReason(choice);
                }
              }}
            >
              {choice}
            </button>
          ))}
        </div>
      )}
      <label className="field field-wide">
        <span>{label}</span>
        <textarea
          ref={area}
          rows={3}
          value={reason}
          placeholder={placeholder}
          maxLength={1000}
          aria-describedby={hintId}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      <p id={hintId} className="quiet">
        {long ? note : `Write at least ${minLength} characters. ${note}`}
      </p>
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onCancel}>
          Cancel
        </button>
        <button
          type="button"
          className="button button-primary"
          disabled={!long}
          onClick={() => onConfirm(reason.trim())}
        >
          {confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}
