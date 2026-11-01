import { useId, useState, type ReactNode } from "react";

import type { EntryPatch } from "../api/client";
import { amountInput, parseMinor } from "../lib/money";
import Icon from "../ui/Icon";
import { useReview } from "./context";
import { inputId, type FieldKey } from "./fields";

/** Label, input, and what the page says about this value: found (with a way to see it) or not. */
export function FieldShell({
  fieldKey,
  label,
  children,
  error,
  errorId,
  wide = false,
  compact = false,
}: {
  fieldKey: FieldKey;
  label: string;
  children: (id: string) => ReactNode;
  error?: string | null;
  errorId?: string;
  wide?: boolean;
  compact?: boolean;
}) {
  const review = useReview();
  const evidence = review.evidence.get(fieldKey);
  const id = inputId(fieldKey);
  return (
    <div
      className={`rfield${review.activeKey === fieldKey ? " rfield-active" : ""}${wide ? " rfield-wide" : ""}${compact ? " rfield-compact" : ""}`}
    >
      <label htmlFor={id} className={compact ? "sr-only" : undefined}>
        {label}
      </label>
      {children(id)}
      <div className="rfield-status">
        {evidence?.found && (
          <button
            type="button"
            className="link-button"
            aria-label={compact ? `Show ${label} on the page` : undefined}
            onClick={() => review.showKey(fieldKey)}
          >
            <Icon name="eye" size={13} />
            {!compact && " Show on page"}
          </button>
        )}
        {evidence && !evidence.found && (
          <span className="rfield-missing" title="Not found on the page">
            <Icon name="alert" size={13} />
            {compact ? <span className="sr-only">Not found on the page</span> : " Not found on the page"}
          </span>
        )}
      </div>
      {error && (
        <p className="rfield-error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

interface TextProps {
  fieldKey: FieldKey;
  label: string;
  value: string | null;
  patch: (value: string | null) => EntryPatch;
  maxLength?: number;
  upper?: boolean;
  pattern?: RegExp;
  problem?: string;
  inputMode?: "text" | "decimal";
  wide?: boolean;
  /** Called with the new text instead of saving it as an entry field (used for line cells). */
  onValue?: (value: string | null) => Promise<boolean>;
  compact?: boolean;
}

/** Text that saves when you leave the box. A bad value is explained and not saved. */
export function TextField({
  fieldKey,
  label,
  value,
  patch,
  maxLength = 200,
  upper = false,
  pattern,
  problem = "That does not look right.",
  inputMode = "text",
  wide,
  onValue,
  compact,
}: TextProps) {
  const review = useReview();
  const [draft, setDraft] = useState(value ?? "");
  const [error, setError] = useState<string | null>(null);
  const errorId = useId();

  async function commit() {
    const text = (upper ? draft.toUpperCase() : draft).trim();
    if ((value ?? "") === text) {
      setError(null);
      return;
    }
    if (text !== "" && pattern && !pattern.test(text)) {
      setError(problem);
      return;
    }
    setError(null);
    const next = text === "" ? null : text;
    const saved = onValue ? await onValue(next) : await review.save(patch(next));
    if (!saved) setDraft(value ?? "");
  }

  return (
    <FieldShell fieldKey={fieldKey} label={label} error={error} errorId={errorId} wide={wide} compact={compact}>
      {(id) => (
        <input
          id={id}
          type="text"
          value={draft}
          maxLength={maxLength}
          inputMode={inputMode}
          readOnly={!review.editable}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onFocus={() => review.setActive(fieldKey)}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
        />
      )}
    </FieldShell>
  );
}

/** An amount in major units ("152.00"), saved as integer minor units. */
export function MoneyField({
  fieldKey,
  label,
  minor,
  patch,
  onMinor,
  compact,
}: {
  fieldKey: FieldKey;
  label: string;
  minor: number | null;
  patch?: (minor: number | null) => EntryPatch;
  onMinor?: (minor: number | null) => Promise<boolean>;
  compact?: boolean;
}) {
  const review = useReview();
  const [draft, setDraft] = useState(amountInput(minor, review.currency));
  const [error, setError] = useState<string | null>(null);
  const errorId = useId();

  async function commit() {
    const parsed = parseMinor(draft, review.currency);
    if (!parsed.ok) {
      setError(parsed.why);
      return;
    }
    setError(null);
    if (parsed.minor === minor) {
      setDraft(amountInput(minor, review.currency));
      return;
    }
    const saved = onMinor ? await onMinor(parsed.minor) : patch ? await review.save(patch(parsed.minor)) : false;
    if (!saved) setDraft(amountInput(minor, review.currency));
  }

  return (
    <FieldShell fieldKey={fieldKey} label={label} error={error} errorId={errorId} compact={compact}>
      {(id) => (
        <input
          id={id}
          type="text"
          className="num-input"
          inputMode="decimal"
          value={draft}
          readOnly={!review.editable}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onFocus={() => review.setActive(fieldKey)}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
        />
      )}
    </FieldShell>
  );
}

export function DateField({
  fieldKey,
  label,
  value,
  patch,
}: {
  fieldKey: FieldKey;
  label: string;
  value: string | null;
  patch: (value: string | null) => EntryPatch;
}) {
  const review = useReview();
  const [draft, setDraft] = useState(value ?? "");
  return (
    <FieldShell fieldKey={fieldKey} label={label}>
      {(id) => (
        <input
          id={id}
          type="date"
          value={draft}
          readOnly={!review.editable}
          disabled={!review.editable}
          onFocus={() => review.setActive(fieldKey)}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={async () => {
            if ((value ?? "") === draft) return;
            const saved = await review.save(patch(draft === "" ? null : draft));
            if (!saved) setDraft(value ?? "");
          }}
        />
      )}
    </FieldShell>
  );
}

export function SelectField({
  fieldKey,
  label,
  value,
  options,
  patch,
  empty,
}: {
  fieldKey: FieldKey;
  label: string;
  value: string | null;
  options: { value: string; label: string }[];
  patch: (value: string | null) => EntryPatch;
  empty?: string;
}) {
  const review = useReview();
  return (
    <FieldShell fieldKey={fieldKey} label={label}>
      {(id) => (
        <select
          id={id}
          value={value ?? ""}
          disabled={!review.editable}
          onFocus={() => review.setActive(fieldKey)}
          onChange={(event) => void review.save(patch(event.target.value === "" ? null : event.target.value))}
        >
          {empty !== undefined && <option value="">{empty}</option>}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
}
