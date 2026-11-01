import type { Evidence } from "../api/client";

/** A key that names one value on the page and in the form: "total", or "amount:12" for a line. */
export type FieldKey = string;

export const headerKey = (field: string): FieldKey => field;
export const lineKey = (field: string, lineId: number): FieldKey => `${field}:${lineId}`;

export function evidenceKey(row: Pick<Evidence, "field" | "line_id">): FieldKey {
  return row.line_id === null ? row.field : lineKey(row.field, row.line_id);
}

/** An id that is safe in the page and unique per value, so a button can move focus to its input. */
export const inputId = (key: FieldKey): string => `field-${key.replace(":", "-")}`;

export const FIELD_LABEL: Record<string, string> = {
  vendor_name: "Vendor",
  invoice_number: "Invoice number",
  entry_date: "Date",
  due_date: "Due date",
  po_number: "PO number",
  currency: "Currency",
  subtotal: "Subtotal",
  tax_total: "Tax",
  shipping: "Shipping",
  discount: "Discount",
  total: "Total",
  description: "Description",
  quantity: "Quantity",
  unit_price: "Unit price",
  amount: "Amount",
  tax_rate: "Tax rate",
  category: "Category",
  entry_type: "Type",
};

export function labelFor(field: string, lineNumber?: number | null): string {
  const base = FIELD_LABEL[field] ?? field;
  return lineNumber ? `${base} (line ${lineNumber})` : base;
}
