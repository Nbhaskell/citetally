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
