// Test data for the Review screen: a document, its entry, evidence and checks, as the API sends them.

import type { CheckCode, CheckOut, DocumentDetail, EntryOut, Evidence } from "../api/client";

export function entryFixture(overrides: Partial<EntryOut> = {}): EntryOut {
  return {
    id: 1,
    entry_type: "invoice",
    vendor_id: null,
    vendor_name_raw: "Brightway Supply",
    vendor_name: null,
    vendor_match_method: null,
    vendor_match_score: null,
    invoice_number: "INV-2042",
    entry_date: "2026-03-14",
    due_date: null,
    po_number: null,
    currency: "USD",
    subtotal_minor: 21200,
    tax_total_minor: 1996,
    shipping_minor: null,
    discount_minor: null,
    total_minor: 23650,
    category: "SUPPLIES",
    category_source: "model",
    notes: null,
    lines: [
      {
        id: 11,
        entry_id: 1,
        line_number: 3,
        description: "Pipe",
        quantity: "10",
        unit_price: "4.50",
        amount_minor: 4500,
        tax_rate: "0.08",
        created_at: "x",
      },
    ],
    ...overrides,
  };
}

export function checkFixture(
  code: CheckCode,
  detail: Record<string, unknown> = {},
  state: Partial<CheckOut> = {},
): CheckOut {
  return {
    check_code: code,
    blocking: ["REQUIRED_FIELDS", "VALUE_IN_DOCUMENT", "LINE_MATH", "SUBTOTAL_MATCH", "TAX_MATCH", "TOTAL_MATCH", "DUPLICATE_SUSPECT", "UNKNOWN_VENDOR"].includes(code),
    passed: true,
    detail,
    overridden: false,
    override_reason: null,
    overridden_at: null,
    ...state,
  };
}

const ALL: CheckCode[] = [
  "REQUIRED_FIELDS", "VALUE_IN_DOCUMENT", "LINE_MATH", "SUBTOTAL_MATCH", "TAX_MATCH", "TOTAL_MATCH",
  "DUPLICATE_SUSPECT", "UNKNOWN_VENDOR", "AMOUNT_OUTLIER", "DATE_SANITY", "CURRENCY_CHECK",
  "LOW_READ_QUALITY", "AMBIGUOUS_FORMAT", "SUSPICIOUS_TEXT",
];  // prettier-ignore

/** All 14 checks passing, with the given ones replaced. */
export function checksFixture(failing: Partial<Record<CheckCode, CheckOut>> = {}): CheckOut[] {
  return ALL.map((code) => failing[code] ?? checkFixture(code));
}

let evidenceId = 100;
export function evidenceRow(
  field: string,
  printed: string,
  box: [number, number, number, number] | null,
  overrides: Partial<Evidence> = {},
): Evidence {
  evidenceId += 1;
  return {
    id: evidenceId,
    entry_id: 1,
    line_id: null,
    field,
    printed_text: printed,
    found: box !== null,
    page_number: box ? 1 : null,
    x0: box?.[0] ?? null,
    y0: box?.[1] ?? null,
    x1: box?.[2] ?? null,
    y1: box?.[3] ?? null,
    match_score: box ? 1 : null,
    created_at: "x",
    ...overrides,
  } as Evidence;
}

export function detailFixture(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    document: {
      id: 5,
      original_filename: "brightway-march.pdf",
      mime_type: "application/pdf",
      source_kind: "digital_pdf",
      page_count: 1,
      size_bytes: 1000,
      status: "needs_review",
      duplicate_of: null,
      failure_stage: null,
      failure_message: null,
      batch_label: null,
      is_synthetic: true,
      created_at: "2026-03-14T10:00:00.000Z",
      updated_at: "2026-03-14T10:00:30.000Z",
    },
    pages: [
      {
        page_number: 1,
        width_px: 800,
        height_px: 1000,
        read_method: "text_layer",
        ocr_engine: null,
        mean_confidence: null,
        skew_degrees: null,
        word_count: 40,
        text: "Brightway Supply\nInvoice INV-2042\nTotal $236.50",
        image_url: "/api/documents/5/pages/1/image",
      },
    ],
    extraction: null,
    entry: entryFixture(),
    evidence: [
      evidenceRow("vendor_name", "Brightway Supply", [0.1, 0.05, 0.4, 0.08]),
      evidenceRow("total", "$236.50", [0.6, 0.8, 0.8, 0.83]),
    ],
    checks: checksFixture(),
    edits: [],
    reviews: [],
    history: [],
    ...overrides,
  } as DocumentDetail;
}
