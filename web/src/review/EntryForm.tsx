import type { CheckOut, EntryLine, EntryPatch } from "../api/client";
import { formatMinor, percentText, priceText } from "../lib/money";
import Icon from "../ui/Icon";
import { useReview } from "./context";
import { DateField, FieldShell, MoneyField, SelectField, TextField } from "./FormFields";
import { lineKey, type FieldKey } from "./fields";

const TYPES = [
  { value: "invoice", label: "Invoice" },
  { value: "receipt", label: "Receipt" },
  { value: "credit_note", label: "Credit note" },
];

function detailOf(checks: readonly CheckOut[], code: string): Record<string, unknown> | null {
  const found = checks.find((c) => c.check_code === code);
  return found ? found.detail : null;
}

/** The vendor, with how sure the match is in words, and a way to pick another. */
function VendorBlock() {
  const { entry, editable, openVendorPicker } = useReview();
  const how = entry.vendor_match_method;
  const state =
    entry.vendor_id === null
      ? { word: "Unknown vendor", icon: "alert" as const, tone: "warn" }
      : how === "manual" || how === "created"
        ? { word: "Chosen by you", icon: "check" as const, tone: "ok" }
        : { word: "Matched", icon: "check" as const, tone: "ok" };
  return (
    <FieldShell fieldKey="vendor_name" label="Vendor" wide>
      {(id) => (
        <div className="vendor-line">
          <span id={id} tabIndex={-1} className="vendor-name">
            {entry.vendor_name ?? entry.vendor_name_raw ?? "No vendor read"}
          </span>
          <span className={`chip chip-${state.tone}`}>
            <Icon name={state.icon} size={13} />
            {state.word}
          </span>
          {entry.vendor_id !== null && entry.vendor_name_raw && entry.vendor_name_raw !== entry.vendor_name && (
            <span className="quiet">printed as “{entry.vendor_name_raw}”</span>
          )}
          {editable && (
            <button type="button" className="button button-small" onClick={openVendorPicker}>
              {entry.vendor_id === null ? "Pick vendor…" : "Change vendor…"}
            </button>
          )}
        </div>
      )}
    </FieldShell>
  );
}

function ArithmeticNote({ line, mismatch, cur }: { line: EntryLine; mismatch: Record<string, unknown> | undefined; cur: string }) {
  if (mismatch) {
    return (
      <span className="arith arith-bad">
        <Icon name="alert" size={13} /> Printed {formatMinor(Number(mismatch.stated), cur)}.{" "}
        {line.quantity} × {priceText(line.unit_price, cur)} is {formatMinor(Number(mismatch.expected), cur)}.
      </span>
    );
  }
  if (line.quantity && line.unit_price && line.amount_minor !== null) {
    return (
      <span className="arith arith-ok">
        <Icon name="check" size={13} /> {line.quantity} × {priceText(line.unit_price, cur)} ={" "}
        {formatMinor(line.amount_minor, cur)}
      </span>
    );
  }
  if ((!line.quantity || !line.quantity.trim()) && line.unit_price) {
    return (
      <span className="arith arith-warn">
        <Icon name="alert" size={13} /> No quantity read. Check the page; enter it if the page prints one.
      </span>
    );
  }
  return <span className="arith quiet">Not checked: needs a quantity, a price and an amount.</span>;
}

function LineItems({ lines, checks }: { lines: readonly EntryLine[]; checks: readonly CheckOut[] }) {
  const { entry, currency, editable, save } = useReview();
  const mismatches = (detailOf(checks, "LINE_MATH")?.mismatches as Record<string, unknown>[] | undefined) ?? [];

  const edit = (lineId: number, change: Record<string, unknown>): Promise<boolean> =>
    save({ lines: lines.map((l) => (l.id === lineId ? { id: l.id, ...change } : { id: l.id })) } as EntryPatch);
  const remove = (lineId: number) =>
    save({ lines: lines.filter((l) => l.id !== lineId).map((l) => ({ id: l.id })) });
  const add = () => save({ lines: [...lines.map((l) => ({ id: l.id })), {}] });

  return (
    <section aria-labelledby="lines-title" className="lines">
      <h3 id="lines-title">Line items</h3>
      {lines.length === 0 && <p className="quiet">No line items were read from this document.</p>}
      <ol className="line-list">
        {lines.map((line) => {
          const n = line.line_number;
          const key = (field: string): FieldKey => lineKey(field, line.id);
          return (
            <li key={line.id} className="line">
              <div className="line-cells">
                <TextField
                  compact
                  wide
                  fieldKey={key("description")}
                  label={`Description, line ${n}`}
                  value={line.description}
                  patch={() => ({})}
                  onValue={(v) => edit(line.id, { description: v })}
                  maxLength={500}
                />
                <TextField
                  compact
                  fieldKey={key("quantity")}
                  label={`Quantity, line ${n}`}
                  value={line.quantity}
                  patch={() => ({})}
                  pattern={/^\d+(\.\d+)?$/}
                  problem="Use a number like 4 or 2.5."
                  inputMode="decimal"
                  onValue={(v) => edit(line.id, { quantity: v })}
                />
                <TextField
                  compact
                  fieldKey={key("unit_price")}
                  label={`Unit price, line ${n}`}
                  value={line.unit_price}
                  patch={() => ({})}
                  pattern={/^\d+(\.\d+)?$/}
                  problem="Use a price like 38.00."
                  inputMode="decimal"
                  onValue={(v) => edit(line.id, { unit_price: v })}
                />
                <MoneyField
                  compact
                  fieldKey={key("amount")}
                  label={`Amount, line ${n}`}
                  minor={line.amount_minor}
                  onMinor={(m) => edit(line.id, { amount_minor: m })}
                />
              </div>
              <div className="line-foot">
                <span className="line-number">Line {n}</span>
                <ArithmeticNote line={line} mismatch={mismatches.find((m) => m.line === n)} cur={currency} />
                {line.tax_rate && <span className="quiet">Tax rate {percentText(line.tax_rate)}</span>}
                {editable && (
                  <button
                    type="button"
                    className="link-button"
                    aria-label={`Remove line ${n}`}
                    onClick={() => void remove(line.id)}
                  >
                    Remove
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {editable && (
        <button type="button" className="button button-small" onClick={() => void add()}>
          Add a line
        </button>
      )}
      <span className="sr-only">{entry.lines.length} lines</span>
    </section>
  );
}

function Calculated({ printed, calculated, cur }: { printed: number | null; calculated: number | null; cur: string }) {
  if (calculated === null || printed === null) return <span className="quiet calc">–</span>;
  if (printed === calculated) {
    return (
      <span className="arith arith-ok calc">
        <Icon name="check" size={13} /> Calculated {formatMinor(calculated, cur)}
      </span>
    );
  }
  const difference = Math.abs(printed - calculated);
  return (
    <span className="arith arith-bad calc">
      <Icon name="alert" size={13} /> Printed {formatMinor(printed, cur)}, calculated{" "}
      {formatMinor(calculated, cur)}, difference {formatMinor(difference, cur)}
    </span>
  );
}

function Totals({ checks }: { checks: readonly CheckOut[] }) {
  const { entry, currency } = useReview();
  const sub = detailOf(checks, "SUBTOTAL_MATCH");
  const tax = detailOf(checks, "TAX_MATCH");
  const total = detailOf(checks, "TOTAL_MATCH");
  const n = (d: Record<string, unknown> | null, key: string) =>
    d && d.applicable !== false && typeof d[key] === "number" ? (d[key] as number) : null;
  const rows: {
    key: string;
    label: string;
    minor: number | null;
    patch: (m: number | null) => EntryPatch;
    calculated: number | null;
  }[] = [
    { key: "subtotal", label: "Subtotal", minor: entry.subtotal_minor, patch: (m) => ({ subtotal_minor: m }), calculated: n(sub, "lines_sum") },
    { key: "tax_total", label: "Tax", minor: entry.tax_total_minor, patch: (m) => ({ tax_total_minor: m }), calculated: tax?.rate_printed === true ? n(tax, "expected") : null },
    { key: "shipping", label: "Shipping", minor: entry.shipping_minor, patch: (m) => ({ shipping_minor: m }), calculated: null },
    { key: "discount", label: "Discount", minor: entry.discount_minor, patch: (m) => ({ discount_minor: m }), calculated: null },
    { key: "total", label: "Total", minor: entry.total_minor, patch: (m) => ({ total_minor: m }), calculated: n(total, "expected") },
  ];
  return (
    <section aria-labelledby="totals-title" className="totals">
      <h3 id="totals-title">Totals as printed</h3>
      {rows.map((row) => (
        <div className="total-row" key={row.key}>
          <MoneyField fieldKey={row.key} label={row.label} minor={row.minor} patch={row.patch} />
          <Calculated printed={row.minor} calculated={row.calculated} cur={currency} />
        </div>
      ))}
    </section>
  );
}

export default function EntryForm({ lines, checks }: { lines: readonly EntryLine[]; checks: readonly CheckOut[] }) {
  const { entry, categories } = useReview();
  return (
    <div className="entry-form">
      <section aria-labelledby="header-title" className="header-fields">
        <h3 id="header-title">Details</h3>
        <SelectField
          fieldKey="entry_type"
          label="Type"
          value={entry.entry_type}
          options={TYPES}
          patch={(v) => ({ entry_type: v as EntryPatch["entry_type"] })}
        />
        <VendorBlock />
        <TextField
          key={`inv-${entry.invoice_number ?? ""}`}
          fieldKey="invoice_number"
          label="Invoice number"
          value={entry.invoice_number}
          patch={(v) => ({ invoice_number: v })}
        />
        <DateField key={`d-${entry.entry_date ?? ""}`} fieldKey="entry_date" label="Date" value={entry.entry_date} patch={(v) => ({ entry_date: v })} />
        <DateField key={`due-${entry.due_date ?? ""}`} fieldKey="due_date" label="Due date" value={entry.due_date} patch={(v) => ({ due_date: v })} />
        <TextField
          key={`po-${entry.po_number ?? ""}`}
          fieldKey="po_number"
          label="PO number"
          value={entry.po_number}
          patch={(v) => ({ po_number: v })}
        />
        <TextField
          key={`cur-${entry.currency ?? ""}`}
          fieldKey="currency"
          label="Currency"
          value={entry.currency}
          patch={(v) => ({ currency: v })}
          maxLength={3}
          upper
          pattern={/^[A-Z]{3}$/}
          problem="Use a three-letter code like USD."
        />
        <SelectField
          fieldKey="category"
          label="Category"
          value={entry.category}
          empty="Choose a category"
          options={categories.filter((c) => c.is_active || c.code === entry.category).map((c) => ({ value: c.code, label: c.name }))}
          patch={(v) => ({ category: v })}
        />
      </section>
      <LineItems lines={lines} checks={checks} />
      <Totals checks={checks} />
    </div>
  );
}
