# Backend Schema: Citetally

Version 0.1. This file is the single source of truth for enum values, statuses, check codes and table names. The PRD, TRD, AppFlow and UI brief use these exact strings.

Database: SQLite in WAL mode with foreign keys on (`PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;`). SQL is kept portable so a move to PostgreSQL is a small change (`INTEGER PRIMARY KEY AUTOINCREMENT` becomes `BIGSERIAL`, `TEXT` timestamps become `TIMESTAMPTZ`, JSON `TEXT` becomes `JSONB`).

Conventions
- Ids are integers. Timestamps are ISO 8601 UTC strings. Booleans are `0/1`. Every table has `created_at`.
- **Money is never a float.** Amounts are stored as integer minor units (cents) in columns ending `_minor`, with an ISO 4217 `currency` code beside them. Quantities and unit prices are stored as exact decimal strings (`TEXT`) and handled with Python `Decimal`. Rounding is round-half-up to the minor unit.
- Credit notes store positive amounts; `entry_type = 'credit_note'` makes exports negative.
- Dates are ISO `YYYY-MM-DD`.
- JSON columns hold JSON text validated by Pydantic in code.
- Coordinates are normalized to the page: `x0, y0, x1, y1` between 0 and 1, origin at the top left.

## 1. Enumerations

| Name | Values |
|---|---|
| `entry_type` | `invoice`, `receipt`, `credit_note` |
| `source_kind` | `digital_pdf`, `scanned_pdf`, `image` |
| `read_method` | `text_layer`, `ocr` |
| `extract_mode` | `text_only`, `text_and_image` |
| `document_status` | `received`, `read`, `extracted`, `needs_review`, `approved`, `rejected`, `exported`, `failed`, `duplicate` |
| `stage` | `ingest`, `read`, `extract`, `ground`, `match`, `check` |
| `check_code` | `REQUIRED_FIELDS`, `VALUE_IN_DOCUMENT`, `LINE_MATH`, `SUBTOTAL_MATCH`, `TAX_MATCH`, `TOTAL_MATCH`, `DUPLICATE_SUSPECT`, `UNKNOWN_VENDOR`, `AMOUNT_OUTLIER`, `DATE_SANITY`, `CURRENCY_CHECK`, `LOW_READ_QUALITY`, `AMBIGUOUS_FORMAT`, `SUSPICIOUS_TEXT` |
| `field` (header) | `vendor_name`, `invoice_number`, `entry_date`, `due_date`, `po_number`, `currency`, `subtotal`, `tax_total`, `shipping`, `discount`, `total` |
| `field` (line) | `description`, `quantity`, `unit_price`, `amount` |
| `decision` | `approve`, `reject`, `reopen`, `mark_duplicate` |
| `vendor_match_method` | `exact`, `alias`, `fuzzy`, `manual`, `created` |
| `category_source` | `vendor_default`, `model`, `manual` |
| `export_profile` | `lines_csv`, `entries_csv` |
| `provider` | `ollama`, `hosted` |

### Check codes: default severity

Blocking checks must pass, or be overridden by the reviewer with a written reason, before an entry can be approved. Non-blocking checks are shown and recorded but never stop approval.

| Check code | Blocking | What it tests |
|---|---|---|
| `REQUIRED_FIELDS` | yes | Vendor, entry date, total and category are present; invoice number too for `invoice` and `credit_note` |
| `VALUE_IN_DOCUMENT` | yes | Every extracted amount, date and number can be found as text on the page |
| `LINE_MATH` | yes | Quantity times unit price equals the line amount, per line |
| `SUBTOTAL_MATCH` | yes | Line amounts add up to the stated subtotal |
| `TAX_MATCH` | yes | Stated tax matches the stated rate applied to the taxable amount |
| `TOTAL_MATCH` | yes | Subtotal plus tax plus shipping minus discount equals the stated total |
| `DUPLICATE_SUSPECT` | yes | Same vendor and invoice number, or same vendor, total and nearby date, as an existing entry |
| `UNKNOWN_VENDOR` | yes | The vendor is matched or created before approval |
| `AMOUNT_OUTLIER` | no | Total is far from this vendor's usual amount |
| `DATE_SANITY` | no | Future date, due date before entry date, or a very old date |
| `CURRENCY_CHECK` | no | Currency differs from the business default or the vendor's usual |
| `LOW_READ_QUALITY` | no | OCR confidence or image quality is low |
| `AMBIGUOUS_FORMAT` | no | A date or number could be read two ways (for example 03/04/2026) |
| `SUSPICIOUS_TEXT` | no | The page contains instruction-like text aimed at an assistant |

### Required fields per entry type (kept in code, shown for reference)

| Entry type | Required |
|---|---|
| `invoice` | `vendor_name`, `invoice_number`, `entry_date`, `total`, category |
| `credit_note` | `vendor_name`, `invoice_number`, `entry_date`, `total`, category |
| `receipt` | `vendor_name`, `entry_date`, `total`, category |

### Seed categories (editable, invented chart for the demo business)

`SUPPLIES` Supplies, `FOOD` Food and drinks, `CLEANING` Cleaning and laundry, `UTILITIES` Utilities, `REPAIRS` Repairs and maintenance, `INSURANCE` Insurance, `SOFTWARE` Software and subscriptions, `PROFESSIONAL` Professional services, `VEHICLE` Vehicle and fuel, `MARKETING` Marketing, `OTHER` Other.

## 2. Tables

```sql
-- db/migrations/0001_init.sql

CREATE TABLE schema_migrations (
  version     INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  applied_at  TEXT NOT NULL
);

CREATE TABLE categories (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  code        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  is_active   INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL
);

CREATE TABLE vendors (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  name                  TEXT NOT NULL,
  normalized_name       TEXT NOT NULL UNIQUE,      -- lowercase, punctuation and legal suffixes removed
  default_category_id   INTEGER REFERENCES categories(id),
  default_currency      TEXT,
  is_active             INTEGER NOT NULL DEFAULT 1,
  is_synthetic          INTEGER NOT NULL DEFAULT 1,
  created_at            TEXT NOT NULL
);

CREATE TABLE vendor_aliases (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor_id         INTEGER NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
  alias             TEXT NOT NULL,
  normalized_alias  TEXT NOT NULL UNIQUE,
  created_at        TEXT NOT NULL
);

CREATE TABLE documents (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  original_filename TEXT NOT NULL,                 -- display only, never used as a path
  stored_path       TEXT NOT NULL,                 -- under CITETALLY_DATA_DIR, named by hash
  file_sha256       TEXT NOT NULL,
  mime_type         TEXT NOT NULL CHECK (mime_type IN ('application/pdf','image/png','image/jpeg')),
  source_kind       TEXT CHECK (source_kind IN ('digital_pdf','scanned_pdf','image')),
  page_count        INTEGER,
  size_bytes        INTEGER NOT NULL,
  status            TEXT NOT NULL DEFAULT 'received'
                    CHECK (status IN ('received','read','extracted','needs_review','approved',
                                      'rejected','exported','failed','duplicate')),
  duplicate_of      INTEGER REFERENCES documents(id),
  failure_stage     TEXT CHECK (failure_stage IN ('ingest','read','extract','ground','match','check')),
  failure_message   TEXT,
  batch_label       TEXT,
  is_synthetic      INTEGER NOT NULL DEFAULT 1,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
CREATE INDEX idx_documents_status ON documents(status, created_at);
CREATE INDEX idx_documents_sha ON documents(file_sha256);

CREATE TABLE pages (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_number      INTEGER NOT NULL,               -- starts at 1
  image_path       TEXT NOT NULL,                  -- rendered PNG, shown in the review screen
  width_px         INTEGER NOT NULL,
  height_px        INTEGER NOT NULL,
  read_method      TEXT NOT NULL CHECK (read_method IN ('text_layer','ocr')),
  ocr_engine       TEXT,                           -- null when read_method is text_layer
  mean_confidence  REAL,                           -- 0 to 100, null for text_layer
  skew_degrees     REAL,
  word_count       INTEGER NOT NULL,
  words            TEXT NOT NULL,                  -- JSON array, see section 3
  text             TEXT NOT NULL,                  -- layout-preserving reading-order text
  created_at       TEXT NOT NULL,
  UNIQUE (document_id, page_number)
);

CREATE TABLE extractions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  attempt         INTEGER NOT NULL DEFAULT 1,
  provider        TEXT NOT NULL CHECK (provider IN ('ollama','hosted')),
  model           TEXT NOT NULL,
  extract_mode    TEXT NOT NULL CHECK (extract_mode IN ('text_only','text_and_image')),
  prompt_version  TEXT NOT NULL,
  fields          TEXT NOT NULL,                   -- JSON as printed on the page, see section 3
  raw_response    TEXT NOT NULL,
  input_tokens    INTEGER,                         -- null when the provider does not report them
  output_tokens   INTEGER,
  duration_ms     INTEGER,
  created_at      TEXT NOT NULL
);
CREATE INDEX idx_extractions_document ON extractions(document_id, attempt);

CREATE TABLE entries (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id           INTEGER NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id         INTEGER NOT NULL REFERENCES extractions(id),
  entry_type            TEXT NOT NULL CHECK (entry_type IN ('invoice','receipt','credit_note')),
  vendor_id             INTEGER REFERENCES vendors(id),
  vendor_name_raw       TEXT,                      -- vendor name as printed
  vendor_match_method   TEXT CHECK (vendor_match_method IN ('exact','alias','fuzzy','manual','created')),
  vendor_match_score    REAL,
  invoice_number        TEXT,
  entry_date            TEXT,
  due_date              TEXT,
  po_number             TEXT,
  currency              TEXT,
  subtotal_minor        INTEGER,
  tax_total_minor       INTEGER,
  shipping_minor        INTEGER,
  discount_minor        INTEGER,
  total_minor           INTEGER,
  category_id           INTEGER REFERENCES categories(id),
  category_source       TEXT CHECK (category_source IN ('vendor_default','model','manual')),
  notes                 TEXT,
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL
);
CREATE INDEX idx_entries_vendor_number ON entries(vendor_id, invoice_number);
CREATE INDEX idx_entries_vendor_date ON entries(vendor_id, entry_date);

CREATE TABLE entry_lines (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id       INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  line_number    INTEGER NOT NULL,
  description    TEXT,
  quantity       TEXT,                             -- exact decimal string, for example "2.5"
  unit_price     TEXT,                             -- exact decimal string, for example "4.125"
  amount_minor   INTEGER,
  tax_rate       TEXT,                             -- exact decimal string, for example "0.0825", when printed
  created_at     TEXT NOT NULL,
  UNIQUE (entry_id, line_number)
);

CREATE TABLE evidence (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id      INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  line_id       INTEGER REFERENCES entry_lines(id) ON DELETE CASCADE,   -- null for header fields
  field         TEXT NOT NULL CHECK (field IN
                ('vendor_name','invoice_number','entry_date','due_date','po_number','currency',
                 'subtotal','tax_total','shipping','discount','total',
                 'description','quantity','unit_price','amount')),
  printed_text  TEXT NOT NULL,                     -- what the model said the page shows
  found         INTEGER NOT NULL,                  -- 1 if located on the page
  page_number   INTEGER,
  x0 REAL, y0 REAL, x1 REAL, y1 REAL,
  match_score   REAL,                              -- 0 to 1
  created_at    TEXT NOT NULL
);
CREATE INDEX idx_evidence_entry ON evidence(entry_id);

CREATE TABLE checks (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  check_code       TEXT NOT NULL CHECK (check_code IN
                   ('REQUIRED_FIELDS','VALUE_IN_DOCUMENT','LINE_MATH','SUBTOTAL_MATCH','TAX_MATCH',
                    'TOTAL_MATCH','DUPLICATE_SUSPECT','UNKNOWN_VENDOR','AMOUNT_OUTLIER','DATE_SANITY',
                    'CURRENCY_CHECK','LOW_READ_QUALITY','AMBIGUOUS_FORMAT','SUSPICIOUS_TEXT')),
  blocking         INTEGER NOT NULL,
  passed           INTEGER NOT NULL,
  detail           TEXT NOT NULL DEFAULT '{}',     -- JSON, see section 3
  overridden       INTEGER NOT NULL DEFAULT 0,
  override_reason  TEXT,
  overridden_at    TEXT,
  created_at       TEXT NOT NULL,
  UNIQUE (document_id, check_code)
);

CREATE TABLE field_edits (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id     INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  line_id      INTEGER REFERENCES entry_lines(id) ON DELETE SET NULL,
  field        TEXT NOT NULL CHECK (field IN
               ('vendor_name','invoice_number','entry_date','due_date','po_number','currency',
                'subtotal','tax_total','shipping','discount','total',
                'description','quantity','unit_price','amount','category','entry_type')),
  old_value    TEXT,
  new_value    TEXT,
  reviewer     TEXT NOT NULL DEFAULT 'local',
  created_at   TEXT NOT NULL
);
CREATE INDEX idx_field_edits_entry ON field_edits(entry_id, created_at);

CREATE TABLE reviews (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  decision        TEXT NOT NULL CHECK (decision IN ('approve','reject','reopen','mark_duplicate')),
  reason          TEXT,
  edited          INTEGER NOT NULL DEFAULT 0,      -- 1 if any field was changed before this decision
  overrides       INTEGER NOT NULL DEFAULT 0,      -- number of blocking checks overridden
  reviewer        TEXT NOT NULL DEFAULT 'local',
  review_seconds  INTEGER,
  created_at      TEXT NOT NULL
);
CREATE INDEX idx_reviews_document ON reviews(document_id, created_at);

CREATE TABLE exports (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  profile      TEXT NOT NULL CHECK (profile IN ('lines_csv','entries_csv')),
  entry_count  INTEGER NOT NULL,
  row_count    INTEGER NOT NULL,
  file_name    TEXT NOT NULL,
  file_sha256  TEXT NOT NULL,
  created_at   TEXT NOT NULL
);

CREATE TABLE export_items (
  export_id  INTEGER NOT NULL REFERENCES exports(id) ON DELETE CASCADE,
  entry_id   INTEGER NOT NULL REFERENCES entries(id),
  PRIMARY KEY (export_id, entry_id)
);

CREATE TABLE audit_events (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id   INTEGER REFERENCES documents(id) ON DELETE CASCADE,
  event_type    TEXT NOT NULL,                     -- stage_started, stage_finished, stage_failed, status_changed, check_failed, review_recorded, export_created
  stage         TEXT,
  from_status   TEXT,
  to_status     TEXT,
  payload       TEXT NOT NULL DEFAULT '{}',        -- JSON, ids and codes only; never document text or amounts
  request_id    TEXT,
  duration_ms   INTEGER,
  created_at    TEXT NOT NULL
);
CREATE INDEX idx_audit_document ON audit_events(document_id, created_at);

CREATE TABLE settings (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
```

## 3. JSON shapes

**`pages.words`** (array; `c` is null for a PDF text layer)
```json
[{"t": "Total", "x0": 0.612, "y0": 0.823, "x1": 0.661, "y1": 0.841, "c": 96.0},
 {"t": "$412.50", "x0": 0.802, "y0": 0.823, "x1": 0.903, "y1": 0.841, "c": 91.0}]
```
Card-like numbers (Luhn check) are masked in `words` and `text` at read time. The original file is kept untouched.

**`extractions.fields`** (every value is a copy of text printed on the page, or `null`; the model does no arithmetic and no reformatting)
```json
{
  "entry_type": "invoice",
  "vendor_name": "Northfield Pet Supply Co.",
  "invoice_number": "INV-20417",
  "entry_date": "03/14/2026",
  "due_date": "04/13/2026",
  "po_number": null,
  "currency": "$",
  "lines": [
    {"description": "Kibble, 30 lb bag", "quantity": "4", "unit_price": "$38.00", "amount": "$152.00", "tax_rate": null},
    {"description": "Poop bags, case of 500", "quantity": "2", "unit_price": "$21.25", "amount": "$42.50", "tax_rate": null}
  ],
  "subtotal": "$194.50",
  "tax_total": "$16.05",
  "shipping": null,
  "discount": null,
  "total": "$210.55",
  "category_suggestion": "SUPPLIES"
}
```
Code parses these strings into the typed columns (dates, minor units, decimals) and flags a string it cannot parse or parses two ways (`AMBIGUOUS_FORMAT`).

**`checks.detail`** examples
```json
{"failed": [{"field": "total", "printed_text": "$211.55"}]}
{"expected_minor": 21055, "stated_minor": 21155, "difference_minor": 100}
{"lines": [{"line_number": 2, "expected_minor": 4250, "stated_minor": 4520}]}
{"matched": "same_vendor_and_invoice_number", "other_document_id": 41}
{"vendor_median_minor": 18000, "total_minor": 91000, "ratio": 5.06, "history_count": 8}
{"ambiguous": [{"field": "entry_date", "printed_text": "03/04/2026", "readings": ["2026-03-04", "2026-04-03"]}]}
```

**`audit_events.payload`** examples
```json
{"read_method": "ocr", "ocr_engine": "tesseract", "pages": 2, "mean_confidence": 83.4}
{"check": "TOTAL_MATCH", "passed": false}
{"profile": "lines_csv", "entries": 12}
```
No payload may contain page text, vendor names, invoice numbers or amounts. A test enforces this.

## 4. State machine (enforced in code and covered by tests)

Status lives on `documents`. An `entries` row exists once extraction has succeeded.

| From | To | Trigger |
|---|---|---|
| `received` | `read` | text layer or OCR finished for every page |
| `received` | `duplicate` | identical file hash already stored; `duplicate_of` set; nothing else runs |
| `received` | `failed` | file unreadable, too large, wrong type or too many pages |
| `read` | `extracted` | model output valid against the schema |
| `read` | `failed` | model failed twice |
| `extracted` | `needs_review` | grounding, matching and checks finished |
| `extracted` | `failed` | grounding, matching or checks crashed after retry |
| `needs_review` | `approved` | reviewer approves and every blocking check passed or was overridden with a reason |
| `needs_review` | `rejected` | reviewer rejects, reason required |
| `needs_review` | `duplicate` | reviewer marks it as a duplicate of another document |
| `approved` | `needs_review` | reviewer reopens (not allowed once exported) |
| `approved` | `exported` | included in an export file |
| `rejected` | `needs_review` | reviewer reopens |
| `needs_review`, `rejected`, `failed` | `received` or `read` | reprocess from a named stage: `received` re-reads, `read` re-extracts |

`exported` is final. An exported entry can appear in a later export only when the user explicitly includes already-exported entries; its status does not change.

## 5. Queries the API needs

```sql
-- Review queue: needs attention first; blocking problems first within a status
SELECT d.* FROM documents d
WHERE d.status IN ('needs_review','failed')
ORDER BY CASE d.status WHEN 'failed' THEN 0 ELSE 1 END, d.created_at ASC;

-- Duplicate lookup by invoice number
SELECT e.document_id FROM entries e
JOIN documents d ON d.id = e.document_id
WHERE e.vendor_id = ? AND e.invoice_number = ? AND d.status NOT IN ('rejected','duplicate','failed')
  AND e.document_id <> ?;

-- Duplicate lookup by content
SELECT e.document_id FROM entries e
JOIN documents d ON d.id = e.document_id
WHERE e.vendor_id = ? AND e.total_minor = ? AND e.currency = ?
  AND ABS(julianday(e.entry_date) - julianday(?)) <= ?
  AND d.status NOT IN ('rejected','duplicate','failed') AND e.document_id <> ?;

-- Vendor history for outlier check (approved or exported only)
SELECT e.total_minor FROM entries e JOIN documents d ON d.id = e.document_id
WHERE e.vendor_id = ? AND e.currency = ? AND d.status IN ('approved','exported');

-- Field correction rate (which fields do reviewers change most)
SELECT field, COUNT(*) FROM field_edits GROUP BY field ORDER BY COUNT(*) DESC;
```

## 6. Migration rules

- Files in `db/migrations/` are numbered and append-only (`0001_init.sql`, `0002_...`). Never edit an applied migration.
- `python -m citetally.db migrate` applies pending migrations in order inside a transaction and records them in `schema_migrations`.
- A test applies all migrations to an empty database and compares the enum lists in `models.py` with the `CHECK` constraints, so this file and the code cannot drift apart.
- Seed data (categories) loads from `db/seed/categories.json`, not from a migration.

## 7. Files on disk (not database tables)

```
data/                          git-ignored runtime folder (CITETALLY_DATA_DIR)
  files/<sha256>               stored originals, named by hash
  pages/<document_id>/<n>.png  rendered pages
  exports/<export_id>.csv      generated export files
data/synthetic/                generated demo documents, committed only as a small sample
eval/golden/citetally_v1.json  golden set: documents, truth and planted problems, with splits
eval/runs/<run id>.run.json    raw pipeline outputs per document, with provenance
eval/runs/<run id>.scores.json computed metrics
eval/reports/                  Markdown reports
```

Golden item shape (values under `truth` are what is **printed** on the document, even when the document itself contains an error):
```json
{
  "id": "inv-0042",
  "split": "heldout",
  "template_family": "T07",
  "condition": "scan_heavy",
  "file": "data/synthetic/docs/inv-0042.pdf",
  "truth": {
    "entry_type": "invoice",
    "vendor_name": "Northfield Pet Supply Co.",
    "invoice_number": "INV-20417",
    "entry_date": "2026-03-14",
    "due_date": "2026-04-13",
    "currency": "USD",
    "subtotal_minor": 19450,
    "tax_total_minor": 1605,
    "total_minor": 21155,
    "lines": [
      {"description": "Kibble, 30 lb bag", "quantity": "4", "unit_price": "38.00", "amount_minor": 15200},
      {"description": "Poop bags, case of 500", "quantity": "2", "unit_price": "21.25", "amount_minor": 4250}
    ]
  },
  "planted": [{"kind": "total_mismatch", "detail": "printed total is 100 cents above the sum"}],
  "expected_checks": ["TOTAL_MATCH"],
  "expected_duplicate_of": null,
  "notes": "total off by one dollar; a correct reader should flag it, not repair it"
}
```
`condition` is one of `clean_pdf`, `scan_light`, `scan_heavy`, `phone_photo`. `template_family` names the invoice layout; held-out documents come from layouts that never appear in the tuned set. All vendors, addresses, phone numbers and invoice numbers are invented, and every generated page carries the footer "SYNTHETIC TEST DATA".
