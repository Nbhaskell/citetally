import { formatMinor } from "../lib/money";

/**
 * An amount, right-aligned with tabular figures. A credit note shows a minus sign and the word
 * "Credit", so the difference never depends on colour.
 */
export default function Money({
  minor,
  currency,
  credit = false,
}: {
  minor: number | null | undefined;
  currency: string | null | undefined;
  credit?: boolean;
}) {
  if (minor === null || minor === undefined) {
    return (
      <span className="money money-none" title="Not read from the page">
        <span aria-hidden="true">–</span>
        <span className="sr-only">Not read from the page</span>
      </span>
    );
  }
  const text = formatMinor(minor, currency ?? "USD", { credit });
  return (
    <span className={`money${credit ? " money-credit" : ""}`}>
      {credit && minor !== 0 && <span className="money-tag">Credit</span>}
      <span className="money-figure">{text}</span>
    </span>
  );
}
