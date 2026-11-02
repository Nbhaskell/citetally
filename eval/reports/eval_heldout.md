# Evaluation: heldout split

Invented documents only (all vendors, invoices and amounts are made up). Numbers are from saved runs under `eval/runs/`; this report was made from them without calling the model.

## Provenance

|  |  |
|---|---|
| Commit | `f3353cf764` |
| Golden set | `eval\golden\citetally_v1.json` sha256 `d3225050fb55de0c…` |
| Model | ollama / qwen3:8b, temperature 0.0, seed 0 |
| Prompt version | extract-v3 |
| OCR | tesseract (tesseract v5.4.0.20240606) |
| Machine | Windows 11, Python 3.13.15 |
| Documents | 70 (heldout) |
| Passes per setting | baseline: 1 |
| Vendors on the list / earlier entries | 16 / 77 (20 repeated to reach the minimum history) |

## Headline numbers, baseline (first pass; shares pooled over all fields)

| Condition | Docs | Failed | Header fields exact | Money exact | Line F1 | Planted caught | Clean docs with a blocking false alarm | Values found on page |
|---|---|---|---|---|---|---|---|---|
| clean pdf | 17 | 0 | 97.3% (92–99) | 100.0% (93–100) | 88.7% | 60.0% (23–88) | 66.7% (39–86) | 96.0% |
| scan light | 17 | 0 | 80.0% (72–86) | 94.2% (84–98) | 24.5% | 66.7% (21–94) | 57.1% (33–79) | 93.1% |
| scan heavy | 18 | 1 | 10.7% (6–18) | 14.8% (8–27) | 0.0% | 100.0% (21–100) | 94.1% (73–99) | 91.8% |
| phone photo | 18 | 0 | 20.7% (14–29) | 18.9% (11–31) | 1.8% | 50.0% (15–85) | 100.0% (78–100) | 91.4% |
| all | 70 | 1 | 50.7% (46–55) | 56.2% (49–63) | 23.2% | 61.5% (36–82) | 80.7% (69–89) | 92.9% |

Percentages show the 95% Wilson interval in brackets. A document that failed counts every printed field as wrong.

## Header fields, baseline (all conditions)

| Field | Exact | Wrong | Missing | Invented |
|---|---|---|---|---|
| currency | 90.0% (81–95) | 5 | 2 | 0 |
| discount | 42.9% (21–67) | 5 | 3 | 0 |
| due_date | 52.4% (38–67) | 17 | 3 | 1 |
| entry_date | 57.1% (45–68) | 28 | 2 | 0 |
| invoice_number | 44.6% (32–58) | 25 | 6 | 0 |
| po_number | 47.4% (27–68) | 7 | 3 | 0 |
| shipping | 28.6% (12–55) | 7 | 3 | 1 |
| subtotal | 45.7% (35–57) | 23 | 15 | 0 |
| tax_total | 47.6% (33–62) | 14 | 8 | 1 |
| total | 61.4% (50–72) | 17 | 10 | 0 |
| vendor_name | 51.4% (40–63) | 33 | 1 | 0 |

## Planted problems caught, by check code

| Check | Caught |
|---|---|
| AMOUNT_OUTLIER | 100.0% (21–100) |
| CURRENCY_CHECK | 0.0% (0–79) |
| DATE_SANITY | 75.0% (30–95) |
| DUPLICATE_SUSPECT | 50.0% (9–91) |
| LINE_MATH | 100.0% (21–100) |
| TAX_MATCH | 0.0% (0–66) |
| TOTAL_MATCH | 100.0% (21–100) |
| UNKNOWN_VENDOR | 100.0% (21–100) |

By kind of problem:

| Planted kind | Caught |
|---|---|
| amount_outlier | 100.0% (21–100) |
| currency_mismatch | 0.0% (0–79) |
| due_before_entry | 66.7% (21–94) |
| duplicate_content | 0.0% (0–79) |
| duplicate_invoice_number | 100.0% (21–100) |
| future_date | 100.0% (21–100) |
| line_math | 100.0% (21–100) |
| tax_mismatch | 0.0% (0–66) |
| total_mismatch | 100.0% (21–100) |
| unknown_vendor | 100.0% (21–100) |

Other checks that also failed on planted documents: LINE_MATH ×4, LOW_READ_QUALITY ×2, REQUIRED_FIELDS ×5, SUBTOTAL_MATCH ×2, TAX_MATCH ×1, TOTAL_MATCH ×1, UNKNOWN_VENDOR ×2, VALUE_IN_DOCUMENT ×7.

## False alarms on clean documents, by blocking check

| Check (of 57 clean documents) | Failing |
|---|---|
| REQUIRED_FIELDS | 54.4% (42–67) |
| VALUE_IN_DOCUMENT | 52.6% (40–65) |
| LINE_MATH | 17.5% (10–29) |
| SUBTOTAL_MATCH | 22.8% (14–35) |
| TAX_MATCH | 5.3% (2–14) |
| TOTAL_MATCH | 33.3% (22–46) |
| DUPLICATE_SUSPECT | 0.0% (0–6) |
| UNKNOWN_VENDOR | 45.6% (33–58) |

## Speed and size, baseline

| Condition | Median seconds per page | Input tokens (mean) | Output tokens (mean) |
|---|---|---|---|
| scan heavy | 10.5 s | 1002 | 623 |
| phone photo | 7.2 s | 745 | 318 |
| clean pdf | 5.3 s | 762 | 306 |
| scan light | 7.5 s | 777 | 348 |
| all | 7.2 s | 820 | 397 |

## Run-to-run spread

Only one pass of each setting was run, so the spread between passes could not be measured.

## Settings side by side, by condition (first pass)

Each row is one setting on the documents it ran, so rows of the same condition use the same documents. The two columns marked with an asterisk were added after the first results were read, to explain them; they are context and were not used to choose anything.

| Condition | Setting | Docs | Header fields exact | Line F1 | Line F1, quantity ignored* | Planted caught | Clean false alarm | Clean false alarm without VALUE_IN_DOCUMENT* | Median s per page |
|---|---|---|---|---|---|---|---|---|---|
| clean pdf | baseline | 17 | 97.3% | 88.7% | 90.7% | 60.0% | 66.7% | 41.7% | 5.3 s |
| scan light | baseline | 17 | 80.0% | 24.5% | 69.8% | 66.7% | 57.1% | 50.0% | 7.5 s |
| scan heavy | baseline | 18 | 10.7% | 0.0% | 0.0% | 100.0% | 94.1% | 94.1% | 10.5 s |
| phone photo | baseline | 18 | 20.7% | 1.8% | 3.6% | 50.0% | 100.0% | 100.0% | 7.2 s |

## What this cannot tell you

- The documents are invented, with layouts and noise made by one generator. Real invoices are messier; handwriting and unusual formats are absent.
- Truth is known by construction, which is cleaner than real labelling. Planted problems are one per document and of 12 kinds chosen in advance.
- 70 documents per setting. Where a condition has few documents, its interval is wide; read the brackets, not the point values.
- One machine, one local model, one OCR engine. Speed will differ elsewhere.
- The checks are given a vendor list and earlier approved entries built from the fact sheet and the golden file. Real history is messier. See the harness notes in `docs/DECISIONS.md`.
- The model is run at temperature 0 with a fixed seed, so repeated passes are expected to be nearly identical. The spread between passes therefore says little about the spread between different documents, which is what the bootstrap measures.
- A person who wrote the system also wrote the test documents, so they are unseen but not blind.
- The held-out split was opened once, after the development numbers were frozen. It is now spent: any further change made after reading it would have to be tested on a new sealed set.

## Reading list

Documents worth opening by hand (not a failure count):

- **failed to process** (1): crn-0023
- **planted problem missed** (5): crn-0017 (tax_mismatch, clean_pdf), crn-0021 (tax_mismatch, clean_pdf), inv-0126 (duplicate_content, phone_photo), inv-0143 (due_before_entry, phone_photo), rcp-0020 (currency_mismatch, scan_light)
- **false alarm on clean document** (46): crn-0015 (REQUIRED_FIELDS, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), crn-0016 (TOTAL_MATCH, UNKNOWN_VENDOR; phone_photo), crn-0018 (LINE_MATH, SUBTOTAL_MATCH; scan_light), crn-0019 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), crn-0020 (REQUIRED_FIELDS, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), crn-0024 (REQUIRED_FIELDS; phone_photo), crn-0026 (SUBTOTAL_MATCH; scan_light), crn-0028 (TOTAL_MATCH, UNKNOWN_VENDOR; phone_photo), inv-0113 (REQUIRED_FIELDS, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0114 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), inv-0116 (VALUE_IN_DOCUMENT; scan_light), inv-0117 (LINE_MATH, SUBTOTAL_MATCH; scan_heavy), inv-0118 (SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0119 (VALUE_IN_DOCUMENT; clean_pdf), inv-0120 (REQUIRED_FIELDS, UNKNOWN_VENDOR; scan_light), inv-0121 (LINE_MATH, REQUIRED_FIELDS, TAX_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0124 (UNKNOWN_VENDOR; scan_light), inv-0125 (LINE_MATH, REQUIRED_FIELDS, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0127 (REQUIRED_FIELDS, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), inv-0128 (VALUE_IN_DOCUMENT; clean_pdf), inv-0130 (REQUIRED_FIELDS, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR; scan_heavy), inv-0131 (REQUIRED_FIELDS, TOTAL_MATCH; phone_photo), inv-0134 (REQUIRED_FIELDS, UNKNOWN_VENDOR; scan_heavy), inv-0137 (LINE_MATH, UNKNOWN_VENDOR; scan_light), inv-0138 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0139 (REQUIRED_FIELDS, UNKNOWN_VENDOR; phone_photo), inv-0140 (SUBTOTAL_MATCH, TAX_MATCH, VALUE_IN_DOCUMENT; clean_pdf), inv-0142 (TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0144 (VALUE_IN_DOCUMENT; clean_pdf), inv-0146 (REQUIRED_FIELDS, TOTAL_MATCH, UNKNOWN_VENDOR; scan_heavy), inv-0147 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0150 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0151 (LINE_MATH, REQUIRED_FIELDS, UNKNOWN_VENDOR; phone_photo), inv-0154 (REQUIRED_FIELDS, TOTAL_MATCH, UNKNOWN_VENDOR; scan_heavy), rcp-0015 (LINE_MATH, REQUIRED_FIELDS, VALUE_IN_DOCUMENT; clean_pdf), rcp-0017 (REQUIRED_FIELDS, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), rcp-0018 (LINE_MATH, REQUIRED_FIELDS, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), rcp-0019 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; clean_pdf), rcp-0021 (REQUIRED_FIELDS, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), rcp-0022 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; phone_photo), rcp-0023 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; clean_pdf), rcp-0024 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_light), rcp-0025 (REQUIRED_FIELDS, SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), rcp-0026 (LINE_MATH, REQUIRED_FIELDS, VALUE_IN_DOCUMENT; phone_photo), rcp-0027 (REQUIRED_FIELDS, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; clean_pdf), rcp-0028 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_light)
- **header value invented** (3): crn-0019, inv-0138, rcp-0021
