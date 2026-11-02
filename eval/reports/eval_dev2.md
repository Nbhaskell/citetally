# Evaluation: dev2 split

Invented documents only (all vendors, invoices and amounts are made up). Numbers are from saved runs under `eval/runs/`; this report was made from them without calling the model.

## Provenance

|  |  |
|---|---|
| Commit | `9dbc37cc2c` (tree had changes) |
| Golden set | `eval\golden\citetally_v2_dev2.json` sha256 `74087ca2551c2267…` |
| Model | ollama / qwen3:8b, temperature 0.0, seed 0 |
| Prompt version | extract-v3 |
| OCR | tesseract (tesseract v5.4.0.20240606) |
| Machine | Windows 11, Python 3.13.15 |
| Documents | 100 (dev2) |
| Passes per setting | baseline: 1 |
| Vendors on the list / earlier entries | 16 / 86 (16 repeated to reach the minimum history) |

## Headline numbers, baseline (first pass; shares pooled over all fields)

| Condition | Docs | Failed | Header fields exact | Money exact | Line F1 | Planted caught | Clean docs with a blocking false alarm | Values found on page |
|---|---|---|---|---|---|---|---|---|
| clean pdf | 20 | 0 | 96.9% (92–99) | 98.0% (90–100) | 96.6% | 57.1% (25–84) | 61.5% (36–82) | 97.3% |
| scan light | 30 | 0 | 86.0% (80–90) | 92.0% (84–96) | 27.6% | 85.7% (49–97) | 87.0% (68–95) | 93.3% |
| scan heavy | 20 | 0 | 34.1% (26–43) | 30.8% (20–44) | 0.0% | 50.0% (19–81) | 100.0% (78–100) | 92.3% |
| phone photo | 30 | 0 | 49.2% (42–56) | 44.9% (34–56) | 9.5% | 60.0% (31–83) | 95.0% (76–99) | 89.6% |
| all | 100 | 0 | 66.3% (63–70) | 66.3% (60–72) | 28.2% | 63.3% (46–78) | 87.1% (77–93) | 92.6% |

Percentages show the 95% Wilson interval in brackets. A document that failed counts every printed field as wrong.

## By level of damage, baseline (first pass)

| Condition, level | Docs | Header fields exact | Line F1 | Planted caught | Clean false alarm |
|---|---|---|---|---|---|
| clean pdf, clean | 20 | 96.9% | 96.6% | 57.1% | 61.5% |
| phone photo, harsh | 10 | 20.3% | 11.8% | – | 100.0% |
| phone photo, mild | 10 | 80.0% | 9.1% | 80.0% | 100.0% |
| phone photo, typical | 10 | 49.2% | 7.6% | 40.0% | 80.0% |
| scan heavy, harsh | 10 | 6.2% | 0.0% | 0.0% | 100.0% |
| scan heavy, typical | 10 | 62.5% | 0.0% | 100.0% | 100.0% |
| scan light, harsh | 10 | 88.3% | 14.5% | 100.0% | 71.4% |
| scan light, mild | 10 | 85.2% | 47.5% | 50.0% | 100.0% |
| scan light, typical | 10 | 84.6% | 20.9% | 100.0% | 87.5% |

## Header fields, baseline (all conditions)

| Field | Exact | Wrong | Missing | Invented |
|---|---|---|---|---|
| currency | 90.0% (83–94) | 7 | 3 | 0 |
| discount | 40.0% (22–61) | 7 | 5 | 1 |
| due_date | 68.6% (57–78) | 19 | 3 | 4 |
| entry_date | 72.0% (63–80) | 26 | 2 | 0 |
| invoice_number | 73.5% (64–81) | 22 | 4 | 2 |
| po_number | 55.6% (34–75) | 5 | 3 | 3 |
| shipping | 35.0% (18–57) | 6 | 7 | 1 |
| subtotal | 60.0% (47–71) | 16 | 8 | 14 |
| tax_total | 52.7% (40–65) | 14 | 12 | 2 |
| total | 70.0% (60–78) | 19 | 11 | 0 |
| vendor_name | 73.0% (64–81) | 26 | 1 | 0 |

## Planted problems caught, by check code

| Check | Caught |
|---|---|
| AMOUNT_OUTLIER | 100.0% (44–100) |
| CURRENCY_CHECK | 50.0% (9–91) |
| DATE_SANITY | 75.0% (30–95) |
| DUPLICATE_SUSPECT | 16.7% (3–56) |
| LINE_MATH | 100.0% (44–100) |
| REQUIRED_FIELDS | 50.0% (9–91) |
| SUSPICIOUS_TEXT | 0.0% (0–66) |
| TAX_MATCH | 66.7% (21–94) |
| TOTAL_MATCH | 100.0% (44–100) |
| UNKNOWN_VENDOR | 100.0% (34–100) |

By kind of problem:

| Planted kind | Caught |
|---|---|
| amount_outlier | 100.0% (44–100) |
| currency_mismatch | 50.0% (9–91) |
| due_before_entry | 50.0% (9–91) |
| duplicate_content | 0.0% (0–56) |
| duplicate_invoice_number | 33.3% (6–79) |
| future_date | 100.0% (34–100) |
| injection_text | 0.0% (0–66) |
| line_math | 100.0% (44–100) |
| missing_invoice_number | 50.0% (9–91) |
| tax_mismatch | 66.7% (21–94) |
| total_mismatch | 100.0% (44–100) |
| unknown_vendor | 100.0% (34–100) |

Other checks that also failed on planted documents: LINE_MATH ×5, LOW_READ_QUALITY ×7, REQUIRED_FIELDS ×5, SUBTOTAL_MATCH ×9, TAX_MATCH ×2, TOTAL_MATCH ×7, UNKNOWN_VENDOR ×4, VALUE_IN_DOCUMENT ×17.

## False alarms on clean documents, by blocking check

| Check (of 70 clean documents) | Failing |
|---|---|
| REQUIRED_FIELDS | 32.9% (23–44) |
| VALUE_IN_DOCUMENT | 58.6% (47–69) |
| LINE_MATH | 25.7% (17–37) |
| SUBTOTAL_MATCH | 30.0% (21–42) |
| TAX_MATCH | 8.6% (4–17) |
| TOTAL_MATCH | 27.1% (18–39) |
| DUPLICATE_SUSPECT | 0.0% (0–5) |
| UNKNOWN_VENDOR | 24.3% (16–36) |

## Speed and size, baseline

| Condition | Median seconds per page | Input tokens (mean) | Output tokens (mean) |
|---|---|---|---|
| clean pdf | 7.1 s | 848 | 352 |
| scan light | 9.1 s | 837 | 318 |
| scan heavy | 10.3 s | 1011 | 439 |
| phone photo | 10.6 s | 850 | 413 |
| all | 9.5 s | 878 | 378 |

## Run-to-run spread

Only one pass of each setting was run, so the spread between passes could not be measured.

## Settings side by side, by condition (first pass)

Each row is one setting on the documents it ran, so rows of the same condition use the same documents. The two columns marked with an asterisk were added after the first results were read, to explain them; they are context and were not used to choose anything.

| Condition | Setting | Docs | Header fields exact | Line F1 | Line F1, quantity ignored* | Planted caught | Clean false alarm | Clean false alarm without VALUE_IN_DOCUMENT* | Median s per page |
|---|---|---|---|---|---|---|---|---|---|
| clean pdf | baseline | 20 | 96.9% | 96.6% | 96.6% | 57.1% | 61.5% | 15.4% | 7.1 s |
| scan light | baseline | 30 | 86.0% | 27.6% | 59.7% | 85.7% | 87.0% | 78.3% | 9.1 s |
| scan heavy | baseline | 20 | 34.1% | 0.0% | 2.2% | 50.0% | 100.0% | 92.9% | 10.3 s |
| phone photo | baseline | 30 | 49.2% | 9.5% | 15.1% | 60.0% | 95.0% | 90.0% | 10.6 s |

## What this cannot tell you

- The documents are invented, with layouts and noise made by one generator. Real invoices are messier; handwriting and unusual formats are absent.
- Truth is known by construction, which is cleaner than real labelling. Planted problems are one per document and of 12 kinds chosen in advance.
- 100 documents per setting. Where a condition has few documents, its interval is wide; read the brackets, not the point values.
- One machine, one local model, one OCR engine. Speed will differ elsewhere.
- The checks are given a vendor list and earlier approved entries built from the fact sheet and the golden file. Real history is messier. See the harness notes in `docs/DECISIONS.md`.
- The model is run at temperature 0 with a fixed seed, so repeated passes are expected to be nearly identical. The spread between passes therefore says little about the spread between different documents, which is what the bootstrap measures.
- A person who wrote the system also wrote the test documents, so they are unseen but not blind.

## Reading list

Documents worth opening by hand (not a failure count):

- **failed to process** (0): none
- **planted problem missed** (11): d2-inv-0002 (injection_text, clean_pdf), d2-inv-0007 (duplicate_content, scan_heavy), d2-inv-0008 (duplicate_invoice_number, phone_photo), d2-inv-0009 (due_before_entry, phone_photo), d2-inv-0012 (missing_invoice_number, clean_pdf), d2-inv-0028 (currency_mismatch, phone_photo), d2-inv-0032 (duplicate_invoice_number, scan_light), d2-inv-0047 (tax_mismatch, phone_photo), d2-inv-0055 (duplicate_content, scan_heavy), d2-inv-0068 (duplicate_content, clean_pdf), d2-rcp-0003 (injection_text, scan_heavy)
- **false alarm on clean document** (61): d2-inv-0003 (LINE_MATH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_light), d2-inv-0010 (REQUIRED_FIELDS, UNKNOWN_VENDOR; phone_photo), d2-inv-0013 (LINE_MATH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_light), d2-inv-0014 (SUBTOTAL_MATCH, TOTAL_MATCH; scan_light), d2-inv-0016 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), d2-inv-0017 (REQUIRED_FIELDS, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), d2-inv-0019 (LINE_MATH, VALUE_IN_DOCUMENT; phone_photo), d2-inv-0020 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), d2-inv-0021 (VALUE_IN_DOCUMENT; clean_pdf), d2-inv-0022 (VALUE_IN_DOCUMENT; scan_light), d2-inv-0024 (LINE_MATH, REQUIRED_FIELDS; scan_light), d2-inv-0025 (LINE_MATH, TOTAL_MATCH; scan_heavy), d2-inv-0026 (REQUIRED_FIELDS, UNKNOWN_VENDOR; scan_heavy), d2-inv-0027 (LINE_MATH, SUBTOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), d2-inv-0029 (SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), d2-inv-0033 (LINE_MATH, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; scan_light), d2-inv-0034 (VALUE_IN_DOCUMENT; scan_light), d2-inv-0035 (LINE_MATH, SUBTOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), d2-inv-0036 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), d2-inv-0038 (SUBTOTAL_MATCH; phone_photo), d2-inv-0039 (LINE_MATH, SUBTOTAL_MATCH, UNKNOWN_VENDOR; phone_photo), d2-inv-0041 (LINE_MATH, VALUE_IN_DOCUMENT; scan_light), d2-inv-0042 (SUBTOTAL_MATCH; scan_light), d2-inv-0045 (REQUIRED_FIELDS, SUBTOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), d2-inv-0048 (REQUIRED_FIELDS, UNKNOWN_VENDOR; phone_photo), d2-inv-0050 (VALUE_IN_DOCUMENT; clean_pdf), d2-inv-0051 (SUBTOTAL_MATCH, TAX_MATCH, VALUE_IN_DOCUMENT; scan_light), d2-inv-0052 (LINE_MATH, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; scan_light), d2-inv-0053 (REQUIRED_FIELDS, SUBTOTAL_MATCH; scan_light), d2-inv-0054 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), d2-inv-0056 (VALUE_IN_DOCUMENT; phone_photo), d2-inv-0058 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), d2-inv-0059 (SUBTOTAL_MATCH, TAX_MATCH, VALUE_IN_DOCUMENT; clean_pdf), d2-inv-0060 (VALUE_IN_DOCUMENT; clean_pdf), d2-inv-0063 (VALUE_IN_DOCUMENT; scan_heavy), d2-inv-0064 (REQUIRED_FIELDS, TOTAL_MATCH, UNKNOWN_VENDOR; scan_heavy), d2-inv-0067 (REQUIRED_FIELDS, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), d2-inv-0069 (UNKNOWN_VENDOR; clean_pdf), d2-inv-0071 (TOTAL_MATCH; scan_light), d2-inv-0072 (LINE_MATH, SUBTOTAL_MATCH, TAX_MATCH, VALUE_IN_DOCUMENT; scan_light), d2-inv-0074 (REQUIRED_FIELDS, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), d2-inv-0075 (TOTAL_MATCH, UNKNOWN_VENDOR; phone_photo), d2-inv-0076 (REQUIRED_FIELDS, UNKNOWN_VENDOR; phone_photo), d2-inv-0077 (REQUIRED_FIELDS, UNKNOWN_VENDOR; phone_photo), d2-inv-0080 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_light), d2-rcp-0001 (LINE_MATH, REQUIRED_FIELDS, TAX_MATCH; scan_light), d2-rcp-0002 (REQUIRED_FIELDS; scan_heavy), d2-rcp-0004 (SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), d2-rcp-0005 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), d2-rcp-0006 (REQUIRED_FIELDS, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), d2-rcp-0007 (VALUE_IN_DOCUMENT; clean_pdf), d2-rcp-0009 (REQUIRED_FIELDS, TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_light), d2-rcp-0010 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_light), d2-rcp-0012 (REQUIRED_FIELDS, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), d2-rcp-0013 (REQUIRED_FIELDS, UNKNOWN_VENDOR; scan_heavy), d2-rcp-0014 (LINE_MATH, VALUE_IN_DOCUMENT; phone_photo), d2-rcp-0016 (SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), d2-rcp-0017 (VALUE_IN_DOCUMENT; clean_pdf), d2-rcp-0018 (VALUE_IN_DOCUMENT; clean_pdf), d2-rcp-0019 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_light), d2-rcp-0020 (REQUIRED_FIELDS; scan_light)
- **header value invented** (25): d2-inv-0005, d2-inv-0012, d2-inv-0013, d2-inv-0029, d2-inv-0036, d2-inv-0043, d2-inv-0055, d2-inv-0058, d2-inv-0061, d2-inv-0064, d2-inv-0070, d2-inv-0072, d2-inv-0073, d2-inv-0078, d2-rcp-0004, d2-rcp-0005, d2-rcp-0006, d2-rcp-0008, d2-rcp-0011, d2-rcp-0012, d2-rcp-0014, d2-rcp-0015, d2-rcp-0016, d2-rcp-0017, d2-rcp-0020
