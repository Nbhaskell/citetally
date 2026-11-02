-- A page can be read more than once (different Tesseract settings and sizes). `words` stays the
-- merged reading the model and the review screen use; `alt_words` keeps each separate reading
-- (a JSON array of word arrays) so a value can be located in any of them.
ALTER TABLE pages ADD COLUMN alt_words TEXT NOT NULL DEFAULT '[]';
