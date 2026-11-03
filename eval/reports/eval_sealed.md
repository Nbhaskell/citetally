# Evaluation: sealed split

Invented documents only (all vendors, invoices and amounts are made up). Numbers are from saved runs under `eval/runs/`; this report was made from them without calling the model.

## Provenance

|  |  |
|---|---|
| Commit | `6f9285f6c6` |
| Golden set | `data\synthetic\sealed\golden_sealed.json` sha256 `4ad4817e3bc2e803…` |
| Model | ollama / qwen3:8b, temperature 0.0, seed 0 |
| Prompt version | extract-v3 |
| OCR | tesseract (tesseract v5.4.0.20240606) |
| Machine | Windows 11, Python 3.13.15 |
| Documents | 250 (sealed) |
| Passes per setting | final: 1 |
| Vendors on the list / earlier entries | 16 / 177 (2 repeated to reach the minimum history) |

## Headline numbers, final (first pass; shares pooled over all fields)

| Condition | Docs | Failed | Header fields exact | Header value exact* | Money exact | Line F1 | Planted caught | Clean docs with a blocking false alarm | Values found on page |
|---|---|---|---|---|---|---|---|---|---|
| clean pdf | 50 | 0 | 97.4% (95–99) | 97.4% (95–99) | 100.0% (98–100) | 100.0% | 85.7% (65–95) | 6.9% (2–22) | 99.7% |
| scan light | 75 | 0 | 99.4% (98–100) | 99.4% (98–100) | 99.1% (97–100) | 93.8% | 90.0% (70–97) | 20.0% (12–32) | 99.0% |
| scan heavy | 50 | 0 | 93.2% (90–95) | 94.6% (92–97) | 92.0% (87–95) | 77.4% | 64.3% (39–84) | 88.9% (75–96) | 61.4% |
| phone photo | 75 | 0 | 96.0% (94–97) | 96.0% (94–97) | 92.6% (89–95) | 93.8% | 90.0% (70–97) | 67.3% (54–78) | 79.5% |
| all | 250 | 0 | 96.7% (96–97) | 97.0% (96–98) | 95.9% (94–97) | 91.8% | 84.0% (74–91) | 46.9% (40–54) | 85.7% |

Percentages show the 95% Wilson interval in brackets. A document that failed counts every printed field as wrong. *Header value exact counts a field right when it means what the page says: the same amount (a missing "$" is not a different amount), the same date, otherwise the same words. It was added after the first results were read; the target is judged on the stricter exact-text column.

## By level of damage, final (first pass)

| Condition, level | Docs | Header fields exact | Header value exact* | Line F1 | Planted caught | Clean false alarm |
|---|---|---|---|---|---|---|
| clean pdf, clean | 50 | 97.4% | 97.4% | 100.0% | 85.7% | 6.9% |
| phone photo, harsh | 25 | 90.5% | 90.5% | 91.2% | 100.0% | 100.0% |
| phone photo, mild | 25 | 98.2% | 98.2% | 90.5% | 85.7% | 22.2% |
| phone photo, typical | 25 | 99.4% | 99.4% | 100.0% | 85.7% | 77.8% |
| scan heavy, harsh | 25 | 86.1% | 89.2% | 58.8% | 60.0% | 100.0% |
| scan heavy, typical | 25 | 100.0% | 100.0% | 96.4% | 66.7% | 75.0% |
| scan light, harsh | 25 | 99.4% | 99.4% | 91.4% | 90.0% | 6.7% |
| scan light, mild | 25 | 100.0% | 100.0% | 90.1% | 75.0% | 38.1% |
| scan light, typical | 25 | 98.8% | 98.8% | 100.0% | 100.0% | 10.5% |

## Header fields, final (all conditions)

| Field | Exact | Wrong | Missing | Invented |
|---|---|---|---|---|
| currency | 99.6% (98–100) | 1 | 0 | 0 |
| discount | 92.0% (81–97) | 1 | 3 | 2 |
| due_date | 97.1% (93–99) | 4 | 0 | 2 |
| entry_date | 98.4% (96–99) | 3 | 1 | 0 |
| invoice_number | 96.3% (93–98) | 9 | 0 | 1 |
| po_number | 95.7% (85–99) | 1 | 1 | 2 |
| shipping | 94.0% (84–98) | 2 | 1 | 1 |
| subtotal | 96.0% (93–98) | 8 | 2 | 0 |
| tax_total | 95.0% (90–97) | 8 | 0 | 4 |
| total | 98.0% (95–99) | 5 | 0 | 0 |
| vendor_name | 97.6% (95–99) | 6 | 0 | 0 |

## Planted problems caught, by check code

| Check | Caught |
|---|---|
| AMOUNT_OUTLIER | 100.0% (61–100) |
| CURRENCY_CHECK | 83.3% (44–97) |
| DATE_SANITY | 91.7% (65–99) |
| DUPLICATE_SUSPECT | 100.0% (76–100) |
| LINE_MATH | 100.0% (65–100) |
| REQUIRED_FIELDS | 100.0% (61–100) |
| SUSPICIOUS_TEXT | 50.0% (19–81) |
| TAX_MATCH | 0.0% (0–35) |
| TOTAL_MATCH | 100.0% (65–100) |
| UNKNOWN_VENDOR | 100.0% (61–100) |

By kind of problem:

| Planted kind | Caught |
|---|---|
| amount_outlier | 100.0% (61–100) |
| currency_mismatch | 83.3% (44–97) |
| due_before_entry | 83.3% (44–97) |
| duplicate_content | 100.0% (61–100) |
| duplicate_invoice_number | 100.0% (61–100) |
| future_date | 100.0% (61–100) |
| injection_text | 50.0% (19–81) |
| line_math | 100.0% (65–100) |
| missing_invoice_number | 100.0% (61–100) |
| tax_mismatch | 0.0% (0–35) |
| total_mismatch | 100.0% (65–100) |
| unknown_vendor | 100.0% (61–100) |

Other checks that also failed on planted documents: DATE_SANITY ×1, LINE_MATH ×2, LOW_READ_QUALITY ×22, SUBTOTAL_MATCH ×1, VALUE_IN_DOCUMENT ×32.

## False alarms on clean documents, by blocking check

| Check (of 175 clean documents) | Failing |
|---|---|
| REQUIRED_FIELDS | 0.6% (0–3) |
| VALUE_IN_DOCUMENT | 44.6% (37–52) |
| LINE_MATH | 4.6% (2–9) |
| SUBTOTAL_MATCH | 4.0% (2–8) |
| TAX_MATCH | 0.6% (0–3) |
| TOTAL_MATCH | 6.9% (4–12) |
| DUPLICATE_SUSPECT | 0.0% (0–2) |
| UNKNOWN_VENDOR | 0.0% (0–2) |

## Speed and size, final

| Condition | Median seconds per page | Input tokens (mean) | Output tokens (mean) |
|---|---|---|---|
| scan light | 17.2 s | 2718 | 329 |
| scan heavy | 15.6 s | 2958 | 336 |
| phone photo | 16.0 s | 2889 | 341 |
| clean pdf | 9.0 s | 873 | 353 |
| all | 15.1 s | 2449 | 339 |

## Run-to-run spread

Only one pass of each setting was run, so the spread between passes could not be measured.

## Settings side by side, by condition (first pass)

Each row is one setting on the documents it ran, so rows of the same condition use the same documents. The two columns marked with an asterisk were added after the first results were read, to explain them; they are context and were not used to choose anything.

| Condition | Setting | Docs | Header fields exact | Header value exact* | Line F1 | Line F1, quantity ignored* | Planted caught | Clean false alarm | Clean false alarm without VALUE_IN_DOCUMENT* | Median s per page |
|---|---|---|---|---|---|---|---|---|---|---|
| clean pdf | final | 50 | 97.4% | 97.4% | 100.0% | 100.0% | 85.7% | 6.9% | 0.0% | 9.0 s |
| scan light | final | 75 | 99.4% | 99.4% | 93.8% | 99.2% | 90.0% | 20.0% | 7.3% | 17.2 s |
| scan heavy | final | 50 | 93.2% | 94.6% | 77.4% | 79.2% | 64.3% | 88.9% | 25.0% | 15.6 s |
| phone photo | final | 75 | 96.0% | 96.0% | 93.8% | 97.7% | 90.0% | 67.3% | 14.5% | 16.0 s |

## What this cannot tell you

- The documents are invented, with layouts and noise made by one generator. Real invoices are messier; handwriting and unusual formats are absent.
- Truth is known by construction, which is cleaner than real labelling. Planted problems are one per document and of 12 kinds chosen in advance.
- 250 documents per setting. Where a condition has few documents, its interval is wide; read the brackets, not the point values.
- One machine, one local model, one OCR engine. Speed will differ elsewhere.
- The checks are given a vendor list and earlier approved entries built from the fact sheet and the golden file. Real history is messier. See the harness notes in `docs/DECISIONS.md`.
- The model is run at temperature 0 with a fixed seed, so repeated passes are expected to be nearly identical. The spread between passes therefore says little about the spread between different documents, which is what the bootstrap measures.
- A person who wrote the system also wrote the test documents, so they are unseen but not blind.
- The sealed set was run once, with the product's own settings and one pass, after the fixes and the review-screen change were merged. It is now spent: any further change made after reading it would have to be tested on a new sealed set.

## Reading list

Documents worth opening by hand (not a failure count):

- **failed to process** (0): none
- **planted problem missed** (12): s2-crn-0012 (injection_text, scan_heavy), s2-crn-0023 (tax_mismatch, scan_heavy), s2-crn-0047 (tax_mismatch, clean_pdf), s2-inv-0013 (injection_text, scan_light), s2-inv-0021 (due_before_entry, clean_pdf), s2-inv-0038 (tax_mismatch, phone_photo), s2-inv-0051 (tax_mismatch, clean_pdf), s2-inv-0055 (tax_mismatch, scan_heavy), s2-inv-0107 (currency_mismatch, phone_photo), s2-inv-0123 (tax_mismatch, scan_light), s2-inv-0134 (tax_mismatch, scan_heavy), s2-rcp-0044 (injection_text, scan_heavy)
- **false alarm on clean document** (82): s2-crn-0002 (VALUE_IN_DOCUMENT; scan_heavy), s2-crn-0003 (VALUE_IN_DOCUMENT; scan_heavy), s2-crn-0004 (VALUE_IN_DOCUMENT; phone_photo), s2-crn-0005 (VALUE_IN_DOCUMENT; phone_photo), s2-crn-0013 (LINE_MATH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s2-crn-0014 (SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s2-crn-0015 (VALUE_IN_DOCUMENT; phone_photo), s2-crn-0024 (VALUE_IN_DOCUMENT; phone_photo), s2-crn-0025 (VALUE_IN_DOCUMENT; phone_photo), s2-crn-0026 (VALUE_IN_DOCUMENT; phone_photo), s2-crn-0032 (VALUE_IN_DOCUMENT; scan_heavy), s2-crn-0033 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s2-crn-0035 (VALUE_IN_DOCUMENT; phone_photo), s2-crn-0036 (VALUE_IN_DOCUMENT; phone_photo), s2-crn-0039 (VALUE_IN_DOCUMENT; scan_light), s2-crn-0043 (SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s2-crn-0045 (VALUE_IN_DOCUMENT; phone_photo), s2-crn-0050 (VALUE_IN_DOCUMENT; scan_light), s2-inv-0003 (VALUE_IN_DOCUMENT; scan_light), s2-inv-0007 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0012 (VALUE_IN_DOCUMENT; clean_pdf), s2-inv-0014 (VALUE_IN_DOCUMENT; scan_light), s2-inv-0016 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0019 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0020 (TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s2-inv-0026 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0030 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0040 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0041 (VALUE_IN_DOCUMENT; clean_pdf), s2-inv-0043 (SUBTOTAL_MATCH; scan_light), s2-inv-0046 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0047 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0049 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0050 (TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s2-inv-0054 (TAX_MATCH; scan_light), s2-inv-0056 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0059 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s2-inv-0066 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0068 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0069 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0076 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0078 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0079 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0085 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0086 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0096 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0098 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0099 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0104 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0105 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0108 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0114 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0115 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0118 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s2-inv-0121 (VALUE_IN_DOCUMENT; scan_light), s2-inv-0124 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0125 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0127 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0135 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0137 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0138 (VALUE_IN_DOCUMENT; phone_photo), s2-inv-0145 (VALUE_IN_DOCUMENT; scan_heavy), s2-inv-0148 (VALUE_IN_DOCUMENT; phone_photo), s2-rcp-0003 (VALUE_IN_DOCUMENT; scan_heavy), s2-rcp-0004 (VALUE_IN_DOCUMENT; scan_heavy), s2-rcp-0007 (VALUE_IN_DOCUMENT; phone_photo), s2-rcp-0010 (VALUE_IN_DOCUMENT; scan_light), s2-rcp-0013 (VALUE_IN_DOCUMENT; scan_heavy), s2-rcp-0014 (LINE_MATH, VALUE_IN_DOCUMENT; scan_heavy), s2-rcp-0016 (VALUE_IN_DOCUMENT; phone_photo), s2-rcp-0017 (LINE_MATH, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s2-rcp-0020 (LINE_MATH; scan_light), s2-rcp-0023 (VALUE_IN_DOCUMENT; scan_heavy), s2-rcp-0024 (LINE_MATH, VALUE_IN_DOCUMENT; scan_heavy), s2-rcp-0025 (VALUE_IN_DOCUMENT; phone_photo), s2-rcp-0027 (TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s2-rcp-0034 (SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s2-rcp-0037 (LINE_MATH, VALUE_IN_DOCUMENT; phone_photo), s2-rcp-0040 (REQUIRED_FIELDS; scan_light), s2-rcp-0046 (VALUE_IN_DOCUMENT; phone_photo), s2-rcp-0047 (VALUE_IN_DOCUMENT; phone_photo), s2-rcp-0050 (VALUE_IN_DOCUMENT; scan_light)
- **header value invented** (11): s2-crn-0013, s2-crn-0039, s2-inv-0009, s2-inv-0021, s2-inv-0056, s2-inv-0059, s2-inv-0076, s2-inv-0116, s2-inv-0125, s2-inv-0140, s2-inv-0149
