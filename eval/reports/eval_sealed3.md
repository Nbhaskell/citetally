# Evaluation: sealed3 split

Invented documents only (all vendors, invoices and amounts are made up). Numbers are from saved runs under `eval/runs/`; this report was made from them without calling the model.

## Provenance

|  |  |
|---|---|
| Commit | `cd4ee4bafa` |
| Golden set | `data\synthetic\sealed3\golden_sealed3.json` sha256 `ce1becdf85a04740…` |
| Model | ollama / qwen3:8b, temperature 0.0, seed 0 |
| Prompt version | extract-v3 |
| OCR | tesseract (tesseract v5.4.0.20240606, with rapidocr 3.10.0 locating values) |
| Machine | Windows 11, Python 3.13.15 |
| Documents | 300 (sealed3) |
| Passes per setting | final_hybrid: 1 |
| Vendors on the list / earlier entries | 16 / 196 (4 repeated to reach the minimum history) |

## Headline numbers, final_hybrid (first pass; shares pooled over all fields)

| Condition | Docs | Failed | Header fields exact | Header value exact* | Money exact | Line F1 | Planted caught | Clean docs with a blocking false alarm | Values found on page |
|---|---|---|---|---|---|---|---|---|---|
| clean pdf | 60 | 0 | 99.5% (98–100) | 99.5% (98–100) | 100.0% (98–100) | 100.0% | 86.4% (67–95) | 2.6% (0–13) | 99.8% |
| scan light | 90 | 0 | 97.5% (96–98) | 97.7% (96–99) | 98.7% (97–100) | 90.6% | 72.4% (54–85) | 9.8% (5–20) | 99.7% |
| scan heavy | 60 | 0 | 87.0% (84–90) | 90.0% (87–93) | 85.2% (80–89) | 73.0% | 78.3% (58–90) | 64.9% (49–78) | 81.5% |
| phone photo | 90 | 0 | 96.3% (95–98) | 96.3% (95–98) | 94.6% (92–97) | 84.6% | 94.1% (81–98) | 39.3% (28–52) | 96.9% |
| all | 300 | 0 | 95.5% (95–96) | 96.1% (95–97) | 95.1% (94–96) | 87.1% | 83.3% (75–89) | 27.6% (22–34) | 95.2% |

Percentages show the 95% Wilson interval in brackets. A document that failed counts every printed field as wrong. *Header value exact counts a field right when it means what the page says: the same amount (a missing "$" is not a different amount), the same date, otherwise the same words. It was added after the first results were read; the target is judged on the stricter exact-text column.

## By level of damage, final_hybrid (first pass)

| Condition, level | Docs | Header fields exact | Header value exact* | Line F1 | Planted caught | Clean false alarm |
|---|---|---|---|---|---|---|
| clean pdf, clean | 60 | 99.5% | 99.5% | 100.0% | 86.4% | 2.6% |
| phone photo, harsh | 30 | 94.9% | 94.9% | 85.3% | 90.9% | 57.9% |
| phone photo, mild | 30 | 99.5% | 99.5% | 93.9% | 90.9% | 10.5% |
| phone photo, typical | 30 | 94.6% | 94.6% | 73.9% | 100.0% | 50.0% |
| scan heavy, harsh | 30 | 76.0% | 82.0% | 53.3% | 58.3% | 100.0% |
| scan heavy, typical | 30 | 98.1% | 98.1% | 91.8% | 100.0% | 31.6% |
| scan light, harsh | 30 | 95.3% | 95.3% | 79.5% | 45.5% | 10.5% |
| scan light, mild | 30 | 99.5% | 99.5% | 97.8% | 90.9% | 5.3% |
| scan light, typical | 30 | 97.7% | 98.2% | 93.5% | 85.7% | 13.0% |

## Header fields, final_hybrid (all conditions)

| Field | Exact | Wrong | Missing | Invented |
|---|---|---|---|---|
| currency | 98.7% (97–99) | 4 | 0 | 0 |
| discount | 91.7% (85–95) | 6 | 4 | 1 |
| due_date | 95.6% (91–98) | 8 | 0 | 0 |
| entry_date | 88.7% (85–92) | 12 | 22 | 0 |
| invoice_number | 97.6% (95–99) | 7 | 0 | 4 |
| po_number | 100.0% (93–100) | 0 | 0 | 1 |
| shipping | 90.8% (84–95) | 11 | 0 | 0 |
| subtotal | 97.7% (95–99) | 7 | 0 | 0 |
| tax_total | 92.6% (88–95) | 16 | 0 | 0 |
| total | 99.3% (98–100) | 2 | 0 | 0 |
| vendor_name | 99.0% (97–100) | 3 | 0 | 0 |

## Planted problems caught, by check code

| Check | Caught |
|---|---|
| AMOUNT_OUTLIER | 100.0% (68–100) |
| CURRENCY_CHECK | 71.4% (36–92) |
| DATE_SANITY | 75.0% (50–90) |
| DUPLICATE_SUSPECT | 81.2% (57–93) |
| LINE_MATH | 87.5% (53–98) |
| REQUIRED_FIELDS | 75.0% (41–93) |
| SUSPICIOUS_TEXT | 71.4% (45–88) |
| TAX_MATCH | 86.7% (62–96) |
| TOTAL_MATCH | 100.0% (68–100) |
| UNKNOWN_VENDOR | 100.0% (68–100) |

By kind of problem:

| Planted kind | Caught |
|---|---|
| amount_outlier | 100.0% (68–100) |
| currency_mismatch | 71.4% (36–92) |
| due_before_entry | 75.0% (41–93) |
| duplicate_content | 62.5% (31–86) |
| duplicate_invoice_number | 100.0% (68–100) |
| future_date | 75.0% (41–93) |
| injection_text | 71.4% (45–88) |
| line_math | 87.5% (53–98) |
| missing_invoice_number | 75.0% (41–93) |
| tax_mismatch | 86.7% (62–96) |
| total_mismatch | 100.0% (68–100) |
| unknown_vendor | 100.0% (68–100) |

Other checks that also failed on planted documents: AMOUNT_OUTLIER ×2, DATE_SANITY ×1, LINE_MATH ×7, LOW_READ_QUALITY ×36, REQUIRED_FIELDS ×14, SUBTOTAL_MATCH ×3, TAX_MATCH ×3, TOTAL_MATCH ×9, UNKNOWN_VENDOR ×1, VALUE_IN_DOCUMENT ×36.

## False alarms on clean documents, by blocking check

| Check (of 192 clean documents) | Failing |
|---|---|
| REQUIRED_FIELDS | 4.7% (2–9) |
| VALUE_IN_DOCUMENT | 22.9% (18–29) |
| LINE_MATH | 1.0% (0–4) |
| SUBTOTAL_MATCH | 1.6% (1–4) |
| TAX_MATCH | 2.1% (1–5) |
| TOTAL_MATCH | 4.2% (2–8) |
| DUPLICATE_SUSPECT | 0.0% (0–2) |
| UNKNOWN_VENDOR | 0.0% (0–2) |

## Speed and size, final_hybrid

| Condition | Median seconds per page | Input tokens (mean) | Output tokens (mean) |
|---|---|---|---|
| clean pdf | 9.1 s | 841 | 325 |
| scan light | 19.9 s | 2550 | 310 |
| scan heavy | 19.4 s | 2718 | 319 |
| phone photo | 20.0 s | 2852 | 321 |
| all | 18.6 s | 2332 | 318 |

## Run-to-run spread

Only one pass of each setting was run, so the spread between passes could not be measured.

## Settings side by side, by condition (first pass)

Each row is one setting on the documents it ran, so rows of the same condition use the same documents. The two columns marked with an asterisk were added after the first results were read, to explain them; they are context and were not used to choose anything.

| Condition | Setting | Docs | Header fields exact | Header value exact* | Line F1 | Line F1, quantity ignored* | Planted caught | Clean false alarm | Clean false alarm without VALUE_IN_DOCUMENT* | Median s per page |
|---|---|---|---|---|---|---|---|---|---|---|
| clean pdf | final_hybrid | 60 | 99.5% | 99.5% | 100.0% | 100.0% | 86.4% | 2.6% | 0.0% | 9.1 s |
| scan light | final_hybrid | 90 | 97.5% | 97.7% | 90.6% | 99.2% | 72.4% | 9.8% | 6.6% | 19.9 s |
| scan heavy | final_hybrid | 60 | 87.0% | 90.0% | 73.0% | 80.4% | 78.3% | 64.9% | 24.3% | 19.4 s |
| phone photo | final_hybrid | 90 | 96.3% | 96.3% | 84.6% | 95.8% | 94.1% | 39.3% | 8.9% | 20.0 s |

## What this cannot tell you

- The documents are invented, with layouts and noise made by one generator. Real invoices are messier; handwriting and unusual formats are absent.
- Truth is known by construction, which is cleaner than real labelling. Planted problems are one per document and of 12 kinds chosen in advance.
- 300 documents per setting. Where a condition has few documents, its interval is wide; read the brackets, not the point values.
- One machine, one local model, one OCR engine. Speed will differ elsewhere.
- The checks are given a vendor list and earlier approved entries built from the fact sheet and the golden file. Real history is messier. See the harness notes in `docs/DECISIONS.md`.
- The model is run at temperature 0 with a fixed seed, so repeated passes are expected to be nearly identical. The spread between passes therefore says little about the spread between different documents, which is what the bootstrap measures.
- A person who wrote the system also wrote the test documents, so they are unseen but not blind.
- The third sealed set was run once, with the product's own settings and one pass, after the third round of fixes. It is now spent: any further change made after reading it would have to be tested on a new sealed set.

## Reading list

Documents worth opening by hand (not a failure count):

- **failed to process** (0): none
- **planted problem missed** (18): s4-crn-0029 (currency_mismatch, phone_photo), s4-crn-0036 (tax_mismatch, scan_heavy), s4-crn-0044 (missing_invoice_number, scan_light), s4-inv-0021 (missing_invoice_number, clean_pdf), s4-inv-0063 (future_date, scan_light), s4-inv-0073 (due_before_entry, scan_light), s4-inv-0075 (tax_mismatch, scan_heavy), s4-inv-0083 (future_date, scan_light), s4-inv-0086 (duplicate_content, phone_photo), s4-inv-0102 (due_before_entry, scan_light), s4-inv-0105 (injection_text, scan_heavy), s4-inv-0128 (injection_text, clean_pdf), s4-inv-0130 (injection_text, scan_light), s4-rcp-0021 (injection_text, scan_light), s4-rcp-0033 (line_math, scan_heavy), s4-rcp-0051 (currency_mismatch, scan_light), s4-rcp-0053 (duplicate_content, scan_heavy), s4-rcp-0057 (duplicate_content, clean_pdf)
- **false alarm on clean document** (53): s4-crn-0006 (VALUE_IN_DOCUMENT; scan_heavy), s4-crn-0009 (VALUE_IN_DOCUMENT; phone_photo), s4-crn-0015 (VALUE_IN_DOCUMENT; scan_heavy), s4-crn-0019 (VALUE_IN_DOCUMENT; phone_photo), s4-crn-0026 (VALUE_IN_DOCUMENT; scan_heavy), s4-crn-0028 (VALUE_IN_DOCUMENT; phone_photo), s4-crn-0046 (VALUE_IN_DOCUMENT; scan_heavy), s4-crn-0058 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0017 (LINE_MATH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0027 (TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0037 (TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0039 (LINE_MATH, SUBTOTAL_MATCH; phone_photo), s4-inv-0047 (VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0062 (REQUIRED_FIELDS; scan_light), s4-inv-0065 (TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0067 (REQUIRED_FIELDS; phone_photo), s4-inv-0077 (REQUIRED_FIELDS, TAX_MATCH, TOTAL_MATCH; phone_photo), s4-inv-0078 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0087 (SUBTOTAL_MATCH; phone_photo), s4-inv-0093 (REQUIRED_FIELDS; scan_light), s4-inv-0094 (REQUIRED_FIELDS; scan_heavy), s4-inv-0095 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0103 (REQUIRED_FIELDS; scan_light), s4-inv-0108 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0112 (REQUIRED_FIELDS; scan_light), s4-inv-0115 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0123 (VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0124 (VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0127 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0131 (VALUE_IN_DOCUMENT; scan_light), s4-inv-0136 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0140 (VALUE_IN_DOCUMENT; scan_light), s4-inv-0147 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0148 (VALUE_IN_DOCUMENT; clean_pdf), s4-inv-0154 (VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0157 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0164 (VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0165 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0166 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0174 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_heavy), s4-inv-0175 (VALUE_IN_DOCUMENT; phone_photo), s4-inv-0177 (SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s4-rcp-0002 (VALUE_IN_DOCUMENT; scan_heavy), s4-rcp-0003 (VALUE_IN_DOCUMENT; scan_heavy), s4-rcp-0006 (VALUE_IN_DOCUMENT; phone_photo), s4-rcp-0012 (VALUE_IN_DOCUMENT; scan_heavy), s4-rcp-0013 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s4-rcp-0016 (VALUE_IN_DOCUMENT; phone_photo), s4-rcp-0023 (VALUE_IN_DOCUMENT; scan_heavy), s4-rcp-0032 (VALUE_IN_DOCUMENT; scan_heavy), s4-rcp-0043 (VALUE_IN_DOCUMENT; scan_heavy), s4-rcp-0045 (VALUE_IN_DOCUMENT; phone_photo), s4-rcp-0056 (VALUE_IN_DOCUMENT; phone_photo)
- **header value invented** (6): s4-crn-0020, s4-crn-0044, s4-inv-0021, s4-inv-0056, s4-rcp-0035, s4-rcp-0057
