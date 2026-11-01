-- A printed line tax rate is located on the page like every other value, so `tax_rate` becomes a
-- valid evidence field and a valid edit field. SQLite cannot change a CHECK in place: both tables
-- are rebuilt and their rows copied. Nothing references either table.

CREATE TABLE evidence_new (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id      INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  line_id       INTEGER REFERENCES entry_lines(id) ON DELETE CASCADE,   -- null for header fields
  field         TEXT NOT NULL CHECK (field IN
                ('vendor_name','invoice_number','entry_date','due_date','po_number','currency',
                 'subtotal','tax_total','shipping','discount','total',
                 'description','quantity','unit_price','amount','tax_rate')),
  printed_text  TEXT NOT NULL,                     -- what the model said the page shows
  found         INTEGER NOT NULL,                  -- 1 if located on the page
  page_number   INTEGER,
  x0 REAL, y0 REAL, x1 REAL, y1 REAL,
  match_score   REAL,                              -- 0 to 1
  created_at    TEXT NOT NULL
);
INSERT INTO evidence_new SELECT * FROM evidence;
DROP TABLE evidence;
ALTER TABLE evidence_new RENAME TO evidence;
CREATE INDEX idx_evidence_entry ON evidence(entry_id);

CREATE TABLE field_edits_new (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id     INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  line_id      INTEGER REFERENCES entry_lines(id) ON DELETE SET NULL,
  field        TEXT NOT NULL CHECK (field IN
               ('vendor_name','invoice_number','entry_date','due_date','po_number','currency',
                'subtotal','tax_total','shipping','discount','total',
                'description','quantity','unit_price','amount','tax_rate','category','entry_type')),
  old_value    TEXT,
  new_value    TEXT,
  reviewer     TEXT NOT NULL DEFAULT 'local',
  created_at   TEXT NOT NULL
);
INSERT INTO field_edits_new SELECT * FROM field_edits;
DROP TABLE field_edits;
ALTER TABLE field_edits_new RENAME TO field_edits;
CREATE INDEX idx_field_edits_entry ON field_edits(entry_id, created_at);
