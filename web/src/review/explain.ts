import type { CheckCode, CheckOut, EntryOut, Evidence } from "../api/client";
import { CHECK_TITLE } from "../lib/copy";
import { formatMinor, percentText, priceText } from "../lib/money";
import { shortDate } from "../lib/time";
import { FIELD_LABEL, headerKey, lineKey, type FieldKey } from "./fields";

export interface Explained {
  title: string;
  /** One or more plain sentences with the actual numbers. */
  text: string[];
  /** The value to look at: moves focus to its box and its input. */
  target: FieldKey | null;
  /** Other documents this one is compared with (duplicates). */
  documents: number[];
  /** Offer the vendor picker. */
  pickVendor: boolean;
}

type Detail = Record<string, unknown>;

const num = (d: Detail, key: string): number | null =>
  typeof d[key] === "number" ? (d[key] as number) : null;
const str = (d: Detail, key: string): string | null =>
  typeof d[key] === "string" ? (d[key] as string) : null;
const list = (d: Detail, key: string): Detail[] =>
  Array.isArray(d[key]) ? (d[key] as Detail[]) : [];
const names = (d: Detail, key: string): string[] =>
  Array.isArray(d[key])
    ? (d[key] as unknown[]).filter((x): x is string => typeof x === "string")
    : [];

function listWords(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** The sentence for one check, written from the numbers the code check recorded. */
export function explain(check: CheckOut, entry: EntryOut, evidence: readonly Evidence[]): Explained {
  const code: CheckCode = check.check_code;
  const d = check.detail as Detail;
  const cur = entry.currency ?? "USD";
  const money = (minor: number | null) => (minor === null ? "?" : formatMinor(minor, cur));
  const lineId = (number: number | null) =>
    entry.lines.find((line) => line.line_number === number)?.id ?? null;
  const out: Explained = {
    title: CHECK_TITLE[code],
    text: [],
    target: null,
    documents: [],
    pickVendor: false,
  };

  switch (code) {
    case "REQUIRED_FIELDS": {
      const missing = names(d, "missing");
      const label = (n: string) => (FIELD_LABEL[n] ?? n).toLowerCase();
      const first = missing[0];
      out.text.push(
        missing.length === 1
          ? `${FIELD_LABEL[first] ?? first} is missing.`
          : `Missing: ${listWords(missing.map(label))}.`,
        entry.entry_type === "receipt"
          ? "Receipts need a vendor, a date, a total and a category."
          : "Invoices need a vendor, an invoice number, a date, a total and a category.",
      );
      out.target = first ? headerKey(first) : null;
      out.pickVendor = missing.includes("vendor_name");
      break;
    }
    case "VALUE_IN_DOCUMENT": {
      const missing = list(d, "not_found");
      const shown = missing.slice(0, 3).map((m) => `'${String(m.printed)}'`);
      const more = missing.length > 3 ? ` and ${missing.length - 3} more` : "";
      out.text.push(
        `We couldn't find ${listWords(shown)}${more} on the page. ` +
          (missing.length === 1 ? "It may have been misread." : "They may have been misread.") +
          " Check against the page.",
      );
      const first = missing[0];
      if (first) {
        const field = String(first.field);
        const id = typeof first.line === "number" ? lineId(first.line) : null;
        out.target = id ? lineKey(field, id) : headerKey(field);
      }
      break;
    }
    case "LINE_MATH": {
      const bad = list(d, "mismatches");
      for (const m of bad.slice(0, 3)) {
        const line = entry.lines.find((l) => l.line_number === m.line);
        const sum = line
          ? `${line.quantity} × ${priceText(line.unit_price, cur)}`
          : "quantity × unit price";
        out.text.push(
          `Line ${String(m.line)}: ${sum} is ${money(num(m, "expected"))}, but the page says ${money(num(m, "stated"))}.`,
        );
      }
      if (bad.length > 3) out.text.push(`${bad.length - 3} more lines do not add up.`);
      const id = bad[0] ? lineId(Number(bad[0].line)) : null;
      out.target = id ? lineKey("amount", id) : null;
      break;
    }
    case "SUBTOTAL_MATCH": {
      out.text.push(
        num(d, "lines_without_amount")
          ? "Some lines have no amount, so they cannot be added up. Fill them in or remove them."
          : `The lines add up to ${money(num(d, "lines_sum"))}. The page says the subtotal is ${money(num(d, "stated"))}.`,
      );
      out.target = headerKey("subtotal");
      break;
    }
    case "TAX_MATCH": {
      const rate = entry.lines.find((l) => l.tax_rate)?.tax_rate;
      out.text.push(
        rate
          ? `${percentText(rate)} tax comes to ${money(num(d, "expected"))}. The page says ${money(num(d, "stated"))}.`
          : `The page says ${money(num(d, "stated"))} tax.`,
      );
      if (d.unusual === true) {
        out.text.push(
          `That is ${str(d, "implied_rate")} of the subtotal; this vendor's usual rate is ${str(d, "usual_rate")}.`,
        );
      }
      out.target = headerKey("tax_total");
      break;
    }
    case "TOTAL_MATCH": {
      out.text.push(
        `Subtotal + tax + shipping − discount is ${money(num(d, "expected"))}. The page says ${money(num(d, "stated"))}.`,
      );
      out.target = headerKey("total");
      break;
    }
    case "DUPLICATE_SUSPECT": {
      const matches = list(d, "matches");
      out.documents = matches.map((m) => Number(m.document_id));
      out.text.push(
        matches.some((m) => m.reason === "invoice_number")
          ? "Same vendor and invoice number as another document."
          : "Same vendor, total and a nearby date as another document.",
      );
      break;
    }
    case "UNKNOWN_VENDOR": {
      out.text.push(
        entry.vendor_name_raw
          ? `'${entry.vendor_name_raw}' isn't in your vendor list. Pick an existing vendor or add it.`
          : "No vendor was read from the page. Pick an existing vendor or add one.",
      );
      out.pickVendor = true;
      out.target = headerKey("vendor_name");
      break;
    }
    case "AMOUNT_OUTLIER": {
      const stated = num(d, "stated");
      const median = Number(str(d, "median"));
      const high = d.direction === "high";
      const ratio = stated && median ? (high ? stated / median : median / stated) : null;
      out.text.push(
        ratio
          ? `This is ${ratio.toFixed(1)} times this vendor's usual invoice (${high ? "larger" : "smaller"}).`
          : "This is far from this vendor's usual amount.",
      );
      out.target = headerKey("total");
      break;
    }
    case "DATE_SANITY": {
      const problems = names(d, "problems");
      if (problems.includes("in_the_future")) {
        out.text.push(`The invoice date is in the future (${shortDate(entry.entry_date)}).`);
      }
      if (problems.includes("due_before_entry")) out.text.push("The due date is before the invoice date.");
      if (problems.includes("too_old")) {
        out.text.push(`The invoice date is very old (${shortDate(entry.entry_date)}).`);
      }
      out.target = headerKey(problems.includes("due_before_entry") ? "due_date" : "entry_date");
      break;
    }
    case "CURRENCY_CHECK": {
      out.text.push(`This invoice is in ${str(d, "stated")}. Your usual is ${str(d, "usual")}.`);
      out.target = headerKey("currency");
      break;
    }
    case "LOW_READ_QUALITY": {
      out.text.push("This scan is hard to read, so check every number against the page.");
      const reasons = names(d, "reasons");
      if (reasons.includes("very_few_words")) out.text.push("Very little text was found on it.");
      if (reasons.includes("large_skew")) out.text.push("The page was photographed at a steep angle.");
      break;
    }
    case "AMBIGUOUS_FORMAT": {
      for (const a of list(d, "ambiguous").slice(0, 3)) {
        const field = String(a.field);
        const readings = Array.isArray(a.readings) ? (a.readings as string[]) : [];
        const printed = evidence.find((e) => e.field === field)?.printed_text;
        const shown = readings.map((r) => (/^\d{4}-\d{2}-\d{2}$/.test(r) ? shortDate(r) : r));
        out.text.push(
          `${printed ? `'${printed}'` : (FIELD_LABEL[field] ?? field)} could be read as ${listWords(shown)}. We read it as the first.`,
        );
      }
      const first = list(d, "ambiguous")[0];
      out.target = first ? headerKey(String(first.field)) : null;
      break;
    }
    case "SUSPICIOUS_TEXT": {
      out.text.push(
        "The page includes text addressed to a reader or system. It was ignored. Review as usual.",
      );
      break;
    }
  }
  return out;
}
