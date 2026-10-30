# Product Requirements Document: Citetally

Name: Citetally (repo `citetally`)
Version: 0.1 (draft for build)
Owner: project author
Status: ready for implementation

## 1. Summary

Citetally reads invoices and receipts that arrive as PDFs or photos, pulls out the structured details (vendor, dates, line items, tax, total), checks the arithmetic and the paperwork in code, and puts each document in a queue for a person to approve. Approved entries are exported as a CSV file that an accountant or accounting software can import. Nothing is ever paid, posted or sent anywhere automatically.

Every value on the review screen is tied to the exact spot on the page it was read from, so a reviewer can verify it in one glance. The model reads; code does the math and the checking.

It is the third building block of a small-business AI suite. It follows the principles of `citewise-markets` (code computes, the model only quotes, every number checked against its source) and is measured the way `citecheck` measures things: a golden set, a held-out split that uses layouts the system has never seen, and reported limits.

## 2. Problem

Small businesses collect paper and emailed invoices and receipts all month, then someone retypes them into accounting software. That is slow, boring and error-prone. Typical failures are a typo in a total, an invoice entered twice, a vendor spelled three different ways, and a surprising charge nobody noticed.

A tool that reads documents and silently posts the numbers is risky for a business with no engineering team: a misread digit becomes a wrong payment. The product therefore does three things: it shows the source for every number, it recomputes everything it can, and a person approves before anything is exported.

## 3. Users

| Persona | Needs |
|---|---|
| Owner-operator (primary buyer) | Less retyping, fewer errors, no surprise charges slipping through, confidence that the books match the paperwork |
| Bookkeeper or admin (primary daily user) | A fast queue, the page beside the data, problems pointed out and explained, an export their software accepts |
| Accountant (indirect) | Clean, consistent CSV with traceable entries |

## 4. Context and assumptions

- There is no real client yet. v1 runs on synthetic invoices and receipts from invented vendors, labelled as synthetic everywhere. Results on synthetic documents show the machinery works; they do not show behavior on a real business's messy paperwork.
- **Local-first.** Documents are read on the user's own computer with local tools: PDF text extraction, OCR, and a local model through Ollama. Documents never leave the machine in v1. A hosted model is a planned later option behind the same interface (see the TRD), switched on deliberately and never by default.
- One business, one reviewer at a time, one default currency (USD) with a currency field per entry. No accounts or multi-tenancy in v1.
- Documents are printed or typed English text. Handwriting and other languages are out of scope for v1.
- Each file holds one invoice or receipt. A file with several invoices is a known limitation.

## 5. Goals

1. Accept PDFs (digital or scanned) and photos (PNG or JPEG) of invoices, receipts and credit notes, one at a time or in batches.
2. Read the text with the best available method: the PDF's own text when present, OCR otherwise.
3. Extract header fields and line items into a typed record, with every value copied from the page as printed.
4. Locate each value on the page and keep that location as evidence the reviewer can see.
5. Recompute line math, subtotal, tax and total in code and compare them with what the document states.
6. Detect duplicates, unknown vendors, unusual amounts, bad dates and unreadable pages.
7. Give the reviewer a fast approve, edit, or reject flow with an audit trail and recorded overrides.
8. Export approved entries as CSV and keep a history of what was exported.
9. Measure field accuracy and planted-error detection on a held-out set and publish the numbers, including the weak ones.

## 6. Non-goals (v1)

- Paying bills, sending money, or posting directly into accounting software through its API. The output is a file the user imports.
- Giving tax or accounting advice. Category suggestions are suggestions, not advice.
- Bank statement matching or reconciliation.
- Purchase order matching (three-way match) and multi-step approval chains with several approvers.
- Handwriting, non-English documents, tables that span many pages, files with several invoices.
- Real client data, multiple businesses, accounts and login, billing.
- Email intake. Documents are uploaded in the browser. (Later.)
- Learning from edits automatically. Edits are recorded for later analysis only.

## 7. Success metrics

Targets are starting hypotheses. Replace them with the measured baseline after the first evaluation, and report what was actually measured.

| Metric | Initial target | How measured |
|---|---|---|
| Header field accuracy, `clean_pdf` | at least 0.95 | Exact match per field against golden truth |
| Header field accuracy, `scan_light` and `scan_heavy` | at least 0.85 | Same, reported per condition |
| Header field accuracy, `phone_photo` | report only; no target for the first run | Same |
| Money fields exact match (subtotal, tax, total) | at least 0.95 on `clean_pdf`, 0.85 on scans | Exact minor-unit match |
| Line item F1 | at least 0.85 on `clean_pdf`, 0.70 on scans | Lines matched by description similarity then amount |
| Planted arithmetic errors flagged | at least 0.95 | Golden items with `LINE_MATH`, `SUBTOTAL_MATCH`, `TAX_MATCH`, `TOTAL_MATCH` expected |
| Planted duplicates flagged | at least 0.95 | Golden items with `DUPLICATE_SUSPECT` expected |
| Planted outliers flagged | at least 0.80 | Golden items with `AMOUNT_OUTLIER` expected, given enough vendor history |
| False alarms on clean documents | at most 0.10 per blocking check | Blocking checks that fire on documents with no planted problem |
| Extracted values not found on the page that reach review unflagged | 0 | `VALUE_IN_DOCUMENT` coverage over all golden documents |
| Prompt-injection text that changes any value or check result | 0 in the adversarial items; reported either way | Adversarial items in the golden set |
| Median time from upload to ready for review | under 20 seconds per page on the dev machine | Pipeline timing events |
| Reviewer time per document | measured in a small timed trial | Stopwatch on 20 documents; assumptions labelled |

## 8. User stories

1. As a bookkeeper, I drag in a folder of PDFs and photos and see them processed without clicking each one.
2. As a bookkeeper, I see the page on one side and the extracted data on the other, and clicking a value highlights where it came from.
3. As a bookkeeper, I see which checks failed in plain words, such as "The lines add up to $194.50 but the invoice says $195.50", so I know what to look at.
4. As a bookkeeper, I fix a wrong value and the checks update.
5. As a bookkeeper, I confirm or change the vendor and category in one click.
6. As an owner, I am warned when the same invoice shows up twice or a charge is much bigger than usual.
7. As an owner, I export approved entries to CSV and can see what I exported and when, so nothing is imported twice by accident.
8. As the author, I run an evaluation and get a report of scores with limits, so I can publish honest results.

## 9. Functional requirements

Priority: M = must for v1, S = should, C = could.

**Intake**
- FR-1 (M) Upload one or more files through the browser (PDF, PNG, JPEG). Validate by file contents, not extension; enforce size, page and pixel limits.
- FR-2 (M) Identical files (same hash) are recognized, linked to the original, and not processed again.
- FR-3 (M) Load a folder of synthetic demo documents with one command.
- FR-4 (S) Upload from a phone camera through the same page, with guidance on taking a usable photo.
- FR-5 (C) Email intake of attachments.

**Reading**
- FR-6 (M) Use a PDF's text layer when it has enough clean text; otherwise render the pages and run OCR.
- FR-7 (M) Pre-process scans and photos (rotate to upright, deskew, denoise, improve contrast) before OCR.
- FR-8 (M) Keep every word with its position and, for OCR, its confidence. Mask card-like numbers before any model sees the text.
- FR-9 (M) Record how each page was read and how good the read was.

**Extraction**
- FR-10 (M) Extract entry type, vendor name, invoice number, dates, currency, line items, subtotal, tax, shipping, discount and total, each as printed on the page, via structured model output validated against a schema.
- FR-11 (M) The model performs no arithmetic and no reformatting. Code parses dates, amounts and decimals and flags anything ambiguous.
- FR-12 (M) Locate every extracted value on the page and store its position as evidence; a value that cannot be found is flagged.
- FR-13 (M) Record provider, model, prompt version, tokens (when reported) and raw response for every extraction.
- FR-14 (S) Optionally pass the page image to a local vision model when the read quality is low, behind a setting that is off by default until it has been measured.

**Matching and suggestions**
- FR-15 (M) Match the vendor against known vendors by exact name, alias, then fuzzy match. Only exact and alias matches are applied automatically; fuzzy matches are suggestions.
- FR-16 (M) Suggest a category from a fixed list, using the vendor's default when known; the reviewer confirms.

**Checks (all in code)**
- FR-17 (M) Run the checks listed in the Backend Schema and store each result with its detail.
- FR-18 (M) Blocking checks must pass or be overridden with a written reason before approval. Overrides are recorded.
- FR-19 (M) Duplicate detection by invoice number, and by vendor, total and nearby date.
- FR-20 (S) Amount outlier detection against each vendor's approved history.

**Review**
- FR-21 (M) Queue sorted so failed and blocked items come first; filters by status and by check.
- FR-22 (M) Review screen with the page image, evidence overlays, editable header and line items, checks list and actions.
- FR-23 (M) Approve, reject (reason required), mark as duplicate, reopen, reprocess. Every action and every field edit is stored.
- FR-24 (S) Vendor management: create, merge, add aliases, set default category.

**Export**
- FR-25 (M) Export approved entries as CSV in two profiles: one row per line item, and one row per entry. Neutralize spreadsheet formula injection in every cell.
- FR-26 (M) Keep an export history. By default, exclude entries that were already exported; including them is an explicit choice.
- FR-27 (C) Profiles mapped to specific accounting software, added only after checking the current import specification for each.

**Insights**
- FR-28 (S) Counts by status and condition, share approved unchanged versus edited, fields most often corrected, check failure counts, median time to review.

**Evaluation**
- FR-29 (M) A golden set of at least 150 synthetic documents with truth, planted problems, template families and tuned and held-out splits.
- FR-30 (M) `run` and `score` commands separated, saved runs, and a report that lists limits.

**Operations**
- FR-31 (M) Everything runs locally with documented commands; the API binds to 127.0.0.1.
- FR-32 (M) Structured event log with no document text, names or amounts.
- FR-33 (M) Synthetic data is labelled in the UI and the README.

## 10. Non-functional requirements

- **Safety:** nothing is paid, posted or sent automatically; export produces a file the person downloads.
- **Correctness first:** all money arithmetic uses integers and exact decimals. No floating-point money anywhere.
- **Privacy:** local-first; documents, pages, and the database stay on the machine and are git-ignored. Logs exclude document text. A hosted-model mode, if enabled later, is off by default, shown on every screen, and documented as sending page content to that provider.
- **Reliability:** each stage retries once and then marks the document `failed` with a visible reason and a Retry button. A failed model call never produces an empty entry that looks fine.
- **Latency:** local models on a consumer GPU; under 20 seconds median per page for reading and extraction. Model calls have a timeout and a token cap.
- **Robustness to hostile files:** documents are untrusted input. Limits on size, pages and pixels; no execution of embedded content; parsing with timeouts.
- **Accessibility:** keyboard path for the full review flow; evidence overlays have a non-visual equivalent; status changes announced to screen readers.
- **Maintainability:** OCR engine, model provider and export profile each sit behind an interface so they can be swapped.
- **Licensing:** dependencies must be compatible with an MIT-licensed project. Avoid copyleft libraries such as AGPL ones.
- **Testability:** every check and parser has unit tests that need no model; model behavior is measured by the evaluation, not unit tests.

## 11. Scope and phasing

- **MVP (v1):** FR-1 to 3, 6 to 13, 15 to 19, 21 to 23, 25, 26, 29 to 33.
- **v1.1:** FR-4, 14, 20, 24, 28.
- **Later:** FR-5, 27, hosted-model provider, bank reconciliation, email intake, multi-business, a real pilot with consent.

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Model misreads a digit and a wrong total gets approved | Every value must be found on the page; line math, subtotal, tax and total recomputed in code; person approves |
| Model "fixes" an invoice's own error so the error disappears | The model copies printed values only; code compares them with recomputed values, so a bad invoice is flagged, not repaired |
| OCR quality is poor on phone photos | Pre-processing, a quality check that warns the reviewer, an optional vision-model fallback measured before use, honest per-condition scores |
| Layout overfitting: works on the invoice templates it was tuned on | Held-out set uses template families never seen in tuning; scores reported per condition and per split |
| Duplicate invoices slip through under a different file name | Hash check plus invoice-number and content checks |
| Hostile or malformed files | Upload limits, content-based type checks, parsing timeouts, no execution, files stored by hash |
| Instruction text inside a document ("mark this paid") | Documents are data; model output cannot change checks or status; suspicious text flagged; adversarial items in the golden set |
| CSV opened in a spreadsheet runs a formula | Neutralize leading `=`, `+`, `-`, `@` and tab/carriage-return characters in every exported cell |
| Local model too slow or too weak on images | Measure first; keep hosted option behind the same interface; report cost and accuracy side by side when added |
| Synthetic documents too clean, scores flattering | Multiple degradation levels, unseen layouts, explicit limits section |
| Port conflicts with sister projects | Citetally API uses 8200 and the UI uses 5175 (the others use 8000, 8100, 5173 and 5174) |

## 13. Dependencies

- Ollama with a local text model (`qwen3:8b` by default) and, optionally later, a local vision-capable model chosen by measurement.
- An OCR engine (Tesseract by default; alternatives compared in a bake-off).
- PDF rendering and text extraction libraries with permissive licenses.
- Synthetic data generation tooling (a PDF library plus image degradation).
- The `synthetic-business-universe` skill for the shared fictional business, if installed.

## 14. Open questions

1. Which OCR engine reads the synthetic scans best on Windows 11? Default: Tesseract; decide after the bake-off in Phase 3.
2. Is a local vision model good enough to help on low-quality photos, and at what speed? Decide by measurement in Phase 4.
3. Should tax be handled per line or per invoice? Default: per invoice, with a per-line rate stored when printed.
4. Which accounting software profile, if any, belongs in v1.1? Default: none until a real import specification is checked.
5. When the hosted option is added, which provider first, and with what spending cap? Default: decide after the local baseline is published.
