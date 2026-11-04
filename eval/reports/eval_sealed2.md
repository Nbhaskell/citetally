# Evaluation: sealed2 split

Invented documents only (all vendors, invoices and amounts are made up). Numbers are from saved runs under `eval/runs/`; this report was made from them without calling the model.

## Provenance

|  |  |
|---|---|
| Commit | `8b5446e222` |
| Golden set | `data\synthetic\sealed2\golden_sealed2.json` sha256 `91df9db3f6a25ef9…` |
| Model | ollama / qwen3:8b, temperature 0.0, seed 0 |
| Prompt version | extract-v3 |
| OCR | tesseract (tesseract v5.4.0.20240606) |
| Machine | Windows 11, Python 3.13.15 |
| Documents | 300 (sealed2) |
| Passes per setting | final: 1 |
| Vendors on the list / earlier entries | 16 / 193 (1 repeated to reach the minimum history) |

## Headline numbers, final (first pass; shares pooled over all fields)

| Condition | Docs | Failed | Header fields exact | Header value exact* | Money exact | Line F1 | Planted caught | Clean docs with a blocking false alarm | Values found on page |
|---|---|---|---|---|---|---|---|---|---|
| clean pdf | 60 | 0 | 95.4% (93–97) | 99.0% (97–100) | 99.4% (97–100) | 95.8% | 65.4% (46–81) | 8.8% (3–23) | 100.0% |
| scan light | 90 | 0 | 97.8% (96–99) | 97.8% (96–99) | 95.8% (93–98) | 95.1% | 100.0% (86–100) | 20.9% (13–32) | 98.2% |
| scan heavy | 60 | 0 | 83.1% (79–86) | 84.3% (80–88) | 80.7% (74–86) | 71.8% | 57.1% (39–73) | 90.6% (76–97) | 67.6% |
| phone photo | 90 | 0 | 93.4% (91–95) | 93.8% (92–95) | 89.8% (85–93) | 85.0% | 74.2% (57–86) | 59.3% (47–71) | 83.4% |
| all | 300 | 0 | 93.1% (92–94) | 94.1% (93–95) | 91.7% (90–93) | 87.6% | 73.2% (64–81) | 42.2% (35–49) | 88.4% |

Percentages show the 95% Wilson interval in brackets. A document that failed counts every printed field as wrong. *Header value exact counts a field right when it means what the page says: the same amount (a missing "$" is not a different amount), the same date, otherwise the same words. It was added after the first results were read; the target is judged on the stricter exact-text column.

## By level of damage, final (first pass)

| Condition, level | Docs | Header fields exact | Header value exact* | Line F1 | Planted caught | Clean false alarm |
|---|---|---|---|---|---|---|
| clean pdf, clean | 60 | 95.4% | 99.0% | 95.8% | 65.4% | 8.8% |
| phone photo, harsh | 30 | 90.9% | 91.4% | 84.9% | 90.9% | 94.7% |
| phone photo, mild | 30 | 92.8% | 93.3% | 92.3% | 66.7% | 28.6% |
| phone photo, typical | 30 | 96.5% | 96.5% | 77.3% | 63.6% | 57.9% |
| scan heavy, harsh | 30 | 72.5% | 75.0% | 56.5% | 37.5% | 100.0% |
| scan heavy, typical | 30 | 93.5% | 93.5% | 85.2% | 83.3% | 83.3% |
| scan light, harsh | 30 | 95.4% | 95.4% | 89.4% | 100.0% | 34.6% |
| scan light, mild | 30 | 100.0% | 100.0% | 100.0% | 100.0% | 16.7% |
| scan light, typical | 30 | 98.0% | 98.0% | 95.8% | 100.0% | 8.7% |

## Header fields, final (all conditions)

| Field | Exact | Wrong | Missing | Invented |
|---|---|---|---|---|
| currency | 100.0% (99–100) | 0 | 0 | 0 |
| discount | 98.3% (91–100) | 1 | 0 | 7 |
| due_date | 97.8% (94–99) | 4 | 0 | 2 |
| entry_date | 92.3% (89–95) | 5 | 18 | 0 |
| invoice_number | 93.8% (90–96) | 12 | 6 | 3 |
| po_number | 94.2% (84–98) | 3 | 0 | 0 |
| shipping | 83.3% (72–91) | 7 | 3 | 7 |
| subtotal | 92.1% (88–95) | 3 | 16 | 11 |
| tax_total | 86.3% (81–90) | 16 | 11 | 7 |
| total | 90.7% (87–93) | 17 | 11 | 0 |
| vendor_name | 98.7% (97–99) | 4 | 0 | 0 |

## Planted problems caught, by check code

| Check | Caught |
|---|---|
| AMOUNT_OUTLIER | 75.0% (41–93) |
| CURRENCY_CHECK | 71.4% (36–92) |
| DATE_SANITY | 93.8% (72–99) |
| DUPLICATE_SUSPECT | 93.8% (72–99) |
| LINE_MATH | 100.0% (68–100) |
| REQUIRED_FIELDS | 87.5% (53–98) |
| SUSPICIOUS_TEXT | 7.1% (1–31) |
| TAX_MATCH | 40.0% (20–64) |
| TOTAL_MATCH | 100.0% (68–100) |
| UNKNOWN_VENDOR | 100.0% (68–100) |

By kind of problem:

| Planted kind | Caught |
|---|---|
| amount_outlier | 75.0% (41–93) |
| currency_mismatch | 71.4% (36–92) |
| due_before_entry | 100.0% (68–100) |
| duplicate_content | 87.5% (53–98) |
| duplicate_invoice_number | 100.0% (68–100) |
| future_date | 87.5% (53–98) |
| injection_text | 7.1% (1–31) |
| line_math | 100.0% (68–100) |
| missing_invoice_number | 87.5% (53–98) |
| tax_mismatch | 40.0% (20–64) |
| total_mismatch | 100.0% (68–100) |
| unknown_vendor | 100.0% (68–100) |

Other checks that also failed on planted documents: LINE_MATH ×4, LOW_READ_QUALITY ×36, REQUIRED_FIELDS ×14, SUBTOTAL_MATCH ×6, TAX_MATCH ×1, TOTAL_MATCH ×8, UNKNOWN_VENDOR ×1, VALUE_IN_DOCUMENT ×48.

## False alarms on clean documents, by blocking check

| Check (of 192 clean documents) | Failing |
|---|---|
| REQUIRED_FIELDS | 7.3% (4–12) |
| VALUE_IN_DOCUMENT | 36.5% (30–43) |
| LINE_MATH | 1.0% (0–4) |
| SUBTOTAL_MATCH | 2.1% (1–5) |
| TAX_MATCH | 3.1% (1–7) |
| TOTAL_MATCH | 2.1% (1–5) |
| DUPLICATE_SUSPECT | 0.0% (0–2) |
| UNKNOWN_VENDOR | 0.5% (0–3) |

## Speed and size, final

| Condition | Median seconds per page | Input tokens (mean) | Output tokens (mean) |
|---|---|---|---|
| clean pdf | 9.6 s | 860 | 343 |
| scan light | 17.4 s | 2579 | 319 |
| scan heavy | 17.3 s | 2891 | 310 |
| phone photo | 17.1 s | 2884 | 329 |
| all | 16.4 s | 2389 | 325 |

## Run-to-run spread

Only one pass of each setting was run, so the spread between passes could not be measured.

## Settings side by side, by condition (first pass)

Each row is one setting on the documents it ran, so rows of the same condition use the same documents. The two columns marked with an asterisk were added after the first results were read, to explain them; they are context and were not used to choose anything.

| Condition | Setting | Docs | Header fields exact | Header value exact* | Line F1 | Line F1, quantity ignored* | Planted caught | Clean false alarm | Clean false alarm without VALUE_IN_DOCUMENT* | Median s per page |
|---|---|---|---|---|---|---|---|---|---|---|
| clean pdf | final | 60 | 95.4% | 99.0% | 95.8% | 95.8% | 65.4% | 8.8% | 8.8% | 9.6 s |
| scan light | final | 90 | 97.8% | 97.8% | 95.1% | 95.1% | 100.0% | 20.9% | 6.0% | 17.4 s |
| scan heavy | final | 60 | 83.1% | 84.3% | 71.8% | 74.9% | 57.1% | 90.6% | 28.1% | 17.3 s |
| phone photo | final | 90 | 93.4% | 93.8% | 85.0% | 93.6% | 74.2% | 59.3% | 13.6% | 17.1 s |

## What this cannot tell you

- The documents are invented, with layouts and noise made by one generator. Real invoices are messier; handwriting and unusual formats are absent.
- Truth is known by construction, which is cleaner than real labelling. Planted problems are one per document and of 12 kinds chosen in advance.
- 300 documents per setting. Where a condition has few documents, its interval is wide; read the brackets, not the point values.
- One machine, one local model, one OCR engine. Speed will differ elsewhere.
- The checks are given a vendor list and earlier approved entries built from the fact sheet and the golden file. Real history is messier. See the harness notes in `docs/DECISIONS.md`.
- The model is run at temperature 0 with a fixed seed, so repeated passes are expected to be nearly identical. The spread between passes therefore says little about the spread between different documents, which is what the bootstrap measures.
- A person who wrote the system also wrote the test documents, so they are unseen but not blind.
- The second sealed set was run once, with the product's own settings and one pass, after the second round of fixes. It is now spent: any further change made after reading it would have to be tested on a new sealed set.

## Reading list

Documents worth opening by hand (not a failure count):

- **failed to process** (0): none
- **planted problem missed** (29): s3-crn-0016 (duplicate_content, scan_heavy), s3-crn-0017 (amount_outlier, phone_photo), s3-crn-0035 (injection_text, scan_heavy), s3-crn-0058 (amount_outlier, phone_photo), s3-inv-0027 (injection_text, scan_heavy), s3-inv-0031 (injection_text, clean_pdf), s3-inv-0037 (injection_text, scan_heavy), s3-inv-0048 (injection_text, phone_photo), s3-inv-0051 (tax_mismatch, clean_pdf), s3-inv-0060 (tax_mismatch, phone_photo), s3-inv-0065 (tax_mismatch, scan_heavy), s3-inv-0085 (future_date, scan_heavy), s3-inv-0087 (injection_text, phone_photo), s3-inv-0105 (tax_mismatch, scan_heavy), s3-inv-0106 (injection_text, phone_photo), s3-inv-0110 (injection_text, clean_pdf), s3-inv-0126 (tax_mismatch, phone_photo), s3-inv-0129 (missing_invoice_number, clean_pdf), s3-inv-0134 (tax_mismatch, scan_heavy), s3-inv-0136 (injection_text, phone_photo), s3-inv-0139 (currency_mismatch, clean_pdf), s3-inv-0148 (currency_mismatch, clean_pdf), s3-rcp-0003 (tax_mismatch, scan_heavy), s3-rcp-0012 (tax_mismatch, scan_heavy), s3-rcp-0013 (tax_mismatch, scan_heavy), s3-rcp-0017 (injection_text, clean_pdf), s3-rcp-0023 (injection_text, scan_heavy), s3-rcp-0057 (injection_text, clean_pdf), s3-rcp-0058 (injection_text, clean_pdf)
- **false alarm on clean document** (81): s3-crn-0005 (VALUE_IN_DOCUMENT; scan_heavy), s3-crn-0006 (VALUE_IN_DOCUMENT; scan_heavy), s3-crn-0008 (VALUE_IN_DOCUMENT; phone_photo), s3-crn-0009 (VALUE_IN_DOCUMENT; phone_photo), s3-crn-0012 (VALUE_IN_DOCUMENT; scan_light), s3-crn-0014 (REQUIRED_FIELDS; scan_light), s3-crn-0018 (VALUE_IN_DOCUMENT; phone_photo), s3-crn-0019 (VALUE_IN_DOCUMENT; phone_photo), s3-crn-0024 (REQUIRED_FIELDS; scan_light), s3-crn-0026 (VALUE_IN_DOCUMENT; scan_heavy), s3-crn-0029 (VALUE_IN_DOCUMENT; phone_photo), s3-crn-0033 (VALUE_IN_DOCUMENT; scan_light), s3-crn-0034 (VALUE_IN_DOCUMENT; scan_light), s3-crn-0036 (VALUE_IN_DOCUMENT; scan_heavy), s3-crn-0037 (REQUIRED_FIELDS; phone_photo), s3-crn-0038 (VALUE_IN_DOCUMENT; phone_photo), s3-crn-0039 (TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s3-crn-0044 (REQUIRED_FIELDS; scan_light), s3-crn-0045 (REQUIRED_FIELDS; scan_heavy), s3-crn-0048 (VALUE_IN_DOCUMENT; phone_photo), s3-crn-0052 (VALUE_IN_DOCUMENT; scan_light), s3-crn-0053 (REQUIRED_FIELDS; scan_light), s3-crn-0054 (VALUE_IN_DOCUMENT; scan_light), s3-crn-0055 (VALUE_IN_DOCUMENT; scan_heavy), s3-crn-0056 (VALUE_IN_DOCUMENT; scan_heavy), s3-crn-0057 (REQUIRED_FIELDS; phone_photo), s3-inv-0006 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0007 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0009 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0010 (LINE_MATH, SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s3-inv-0016 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0017 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0020 (TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s3-inv-0029 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0030 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0038 (TAX_MATCH, VALUE_IN_DOCUMENT; phone_photo), s3-inv-0039 (TAX_MATCH, VALUE_IN_DOCUMENT; phone_photo), s3-inv-0040 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0050 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0056 (LINE_MATH; scan_heavy), s3-inv-0059 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0067 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0068 (TAX_MATCH, VALUE_IN_DOCUMENT; phone_photo), s3-inv-0074 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0075 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0076 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0084 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0088 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0094 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0095 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0098 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0104 (REQUIRED_FIELDS, TAX_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0109 (SUBTOTAL_MATCH, TAX_MATCH; clean_pdf), s3-inv-0115 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0118 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0119 (SUBTOTAL_MATCH; clean_pdf), s3-inv-0124 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0138 (SUBTOTAL_MATCH, TOTAL_MATCH; clean_pdf), s3-inv-0147 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0154 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0157 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0163 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0167 (VALUE_IN_DOCUMENT; phone_photo), s3-inv-0173 (VALUE_IN_DOCUMENT; scan_heavy), s3-inv-0175 (VALUE_IN_DOCUMENT; phone_photo), s3-rcp-0001 (VALUE_IN_DOCUMENT; scan_light), s3-rcp-0002 (VALUE_IN_DOCUMENT; scan_heavy), s3-rcp-0005 (VALUE_IN_DOCUMENT; phone_photo), s3-rcp-0021 (VALUE_IN_DOCUMENT; scan_light), s3-rcp-0022 (VALUE_IN_DOCUMENT; scan_heavy), s3-rcp-0026 (VALUE_IN_DOCUMENT; phone_photo), s3-rcp-0031 (VALUE_IN_DOCUMENT; scan_light), s3-rcp-0032 (VALUE_IN_DOCUMENT; scan_heavy), s3-rcp-0033 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_heavy), s3-rcp-0035 (VALUE_IN_DOCUMENT; phone_photo), s3-rcp-0039 (VALUE_IN_DOCUMENT; scan_light), s3-rcp-0043 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), s3-rcp-0044 (VALUE_IN_DOCUMENT; phone_photo), s3-rcp-0051 (VALUE_IN_DOCUMENT; scan_light), s3-rcp-0053 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_heavy), s3-rcp-0056 (VALUE_IN_DOCUMENT; phone_photo)
- **header value invented** (16): s3-crn-0006, s3-crn-0026, s3-inv-0023, s3-inv-0046, s3-inv-0128, s3-inv-0129, s3-inv-0134, s3-inv-0138, s3-inv-0139, s3-inv-0144, s3-inv-0148, s3-inv-0149, s3-inv-0159, s3-inv-0164, s3-inv-0169, s3-inv-0179
