# Evaluation: sealed4 split

Invented documents only (all vendors, invoices and amounts are made up). Numbers are from saved runs under `eval/runs/`; this report was made from them without calling the model.

## Provenance

|  |  |
|---|---|
| Commit | `3e31806170` |
| Golden set | `data\synthetic\sealed4\golden_sealed4.json` sha256 `3251bc319b615581…` |
| Model | ollama / qwen3:8b, temperature 0.0, seed 0 |
| Prompt version | extract-v3 |
| OCR | tesseract (tesseract v5.4.0.20240606, with rapidocr 3.10.0 locating values) |
| Machine | Windows 11, Python 3.13.15 |
| Documents | 300 (sealed4) |
| Passes per setting | final_hybrid: 1 |
| Vendors on the list / earlier entries | 16 / 198 (6 repeated to reach the minimum history) |

## Headline numbers, final_hybrid (first pass; shares pooled over all fields)

| Condition | Docs | Failed | Header fields exact | Header value exact* | Money exact | Line F1 | Planted caught | Clean docs with a blocking false alarm | Values found on page |
|---|---|---|---|---|---|---|---|---|---|
| clean pdf | 60 | 0 | 94.8% (92–97) | 99.3% (98–100) | 100.0% (98–100) | 98.7% | 87.0% (68–95) | 0.0% (0–9) | 100.0% |
| scan light | 90 | 0 | 100.0% (99–100) | 100.0% (99–100) | 100.0% (99–100) | 91.2% | 76.5% (60–88) | 5.4% (2–15) | 100.0% |
| scan heavy | 60 | 0 | 89.7% (86–92) | 92.2% (89–94) | 88.7% (83–92) | 70.3% | 72.7% (52–87) | 57.9% (42–72) | 83.6% |
| phone photo | 90 | 0 | 94.5% (92–96) | 94.5% (92–96) | 92.5% (89–95) | 94.0% | 79.3% (62–90) | 45.9% (34–58) | 98.1% |
| all | 300 | 0 | 95.3% (94–96) | 96.7% (96–97) | 95.5% (94–97) | 89.4% | 78.7% (70–85) | 27.6% (22–34) | 96.1% |

Percentages show the 95% Wilson interval in brackets. A document that failed counts every printed field as wrong. *Header value exact counts a field right when it means what the page says: the same amount (a missing "$" is not a different amount), the same date, otherwise the same words. It was added after the first results were read; the target is judged on the stricter exact-text column.

## By level of damage, final_hybrid (first pass)

| Condition, level | Docs | Header fields exact | Header value exact* | Line F1 | Planted caught | Clean false alarm |
|---|---|---|---|---|---|---|
| clean pdf, clean | 60 | 94.8% | 99.3% | 98.7% | 87.0% | 0.0% |
| phone photo, harsh | 30 | 90.9% | 90.9% | 89.7% | 55.6% | 71.4% |
| phone photo, mild | 30 | 99.0% | 99.0% | 98.0% | 91.7% | 16.7% |
| phone photo, typical | 30 | 93.8% | 93.8% | 94.3% | 87.5% | 45.5% |
| scan heavy, harsh | 30 | 81.3% | 86.2% | 41.2% | 58.3% | 88.9% |
| scan heavy, typical | 30 | 98.1% | 98.1% | 95.0% | 90.0% | 30.0% |
| scan light, harsh | 30 | 100.0% | 100.0% | 92.0% | 92.3% | 11.8% |
| scan light, mild | 30 | 100.0% | 100.0% | 87.9% | 53.8% | 0.0% |
| scan light, typical | 30 | 100.0% | 100.0% | 93.5% | 87.5% | 4.5% |

## Header fields, final_hybrid (all conditions)

| Field | Exact | Wrong | Missing | Invented |
|---|---|---|---|---|
| currency | 99.3% (98–100) | 2 | 0 | 0 |
| discount | 90.0% (80–95) | 3 | 3 | 4 |
| due_date | 98.9% (96–100) | 2 | 0 | 2 |
| entry_date | 92.3% (89–95) | 7 | 16 | 0 |
| invoice_number | 96.2% (93–98) | 10 | 1 | 6 |
| po_number | 100.0% (94–100) | 0 | 0 | 0 |
| shipping | 95.0% (86–98) | 1 | 2 | 4 |
| subtotal | 94.3% (91–96) | 17 | 0 | 0 |
| tax_total | 89.2% (84–93) | 23 | 0 | 4 |
| total | 96.7% (94–98) | 10 | 0 | 0 |
| vendor_name | 99.3% (98–100) | 2 | 0 | 0 |

## Planted problems caught, by check code

| Check | Caught |
|---|---|
| AMOUNT_OUTLIER | 75.0% (41–93) |
| CURRENCY_CHECK | 71.4% (36–92) |
| DATE_SANITY | 100.0% (81–100) |
| DUPLICATE_SUSPECT | 87.5% (64–96) |
| LINE_MATH | 100.0% (68–100) |
| REQUIRED_FIELDS | 87.5% (53–98) |
| SUSPICIOUS_TEXT | 0.0% (0–22) |
| TAX_MATCH | 86.7% (62–96) |
| TOTAL_MATCH | 100.0% (68–100) |
| UNKNOWN_VENDOR | 100.0% (68–100) |

By kind of problem:

| Planted kind | Caught |
|---|---|
| amount_outlier | 75.0% (41–93) |
| currency_mismatch | 71.4% (36–92) |
| due_before_entry | 100.0% (68–100) |
| duplicate_content | 100.0% (68–100) |
| duplicate_invoice_number | 75.0% (41–93) |
| future_date | 100.0% (68–100) |
| injection_text | 0.0% (0–22) |
| line_math | 100.0% (68–100) |
| missing_invoice_number | 87.5% (53–98) |
| tax_mismatch | 86.7% (62–96) |
| total_mismatch | 100.0% (68–100) |
| unknown_vendor | 100.0% (68–100) |

Other checks that also failed on planted documents: LINE_MATH ×2, LOW_READ_QUALITY ×29, REQUIRED_FIELDS ×5, SUBTOTAL_MATCH ×4, TAX_MATCH ×4, TOTAL_MATCH ×6, VALUE_IN_DOCUMENT ×18.

## False alarms on clean documents, by blocking check

| Check (of 192 clean documents) | Failing |
|---|---|
| REQUIRED_FIELDS | 8.8% (6–14) |
| VALUE_IN_DOCUMENT | 17.2% (13–23) |
| LINE_MATH | 4.2% (2–8) |
| SUBTOTAL_MATCH | 6.8% (4–11) |
| TAX_MATCH | 3.6% (2–7) |
| TOTAL_MATCH | 6.8% (4–11) |
| DUPLICATE_SUSPECT | 0.0% (0–2) |
| UNKNOWN_VENDOR | 0.5% (0–3) |

## Speed and size, final_hybrid

| Condition | Median seconds per page | Input tokens (mean) | Output tokens (mean) |
|---|---|---|---|
| clean pdf | 8.6 s | 850 | 324 |
| scan light | 30.0 s | 2766 | 312 |
| scan heavy | 28.2 s | 2978 | 314 |
| phone photo | 31.1 s | 2848 | 320 |
| all | 20.1 s | 2450 | 317 |

## Run-to-run spread

Only one pass of each setting was run, so the spread between passes could not be measured.

## Settings side by side, by condition (first pass)

Each row is one setting on the documents it ran, so rows of the same condition use the same documents. The two columns marked with an asterisk were added after the first results were read, to explain them; they are context and were not used to choose anything.

| Condition | Setting | Docs | Header fields exact | Header value exact* | Line F1 | Line F1, quantity ignored* | Planted caught | Clean false alarm | Clean false alarm without VALUE_IN_DOCUMENT* | Median s per page |
|---|---|---|---|---|---|---|---|---|---|---|
| clean pdf | final_hybrid | 60 | 94.8% | 99.3% | 98.7% | 98.7% | 87.0% | 0.0% | 0.0% | 8.6 s |
| scan light | final_hybrid | 90 | 100.0% | 100.0% | 91.2% | 95.2% | 76.5% | 5.4% | 5.4% | 30.0 s |
| scan heavy | final_hybrid | 60 | 89.7% | 92.2% | 70.3% | 72.4% | 72.7% | 57.9% | 36.8% | 28.2 s |
| phone photo | final_hybrid | 90 | 94.5% | 94.5% | 94.0% | 96.1% | 79.3% | 45.9% | 31.1% | 31.1 s |

## What this cannot tell you

- The documents are invented, with layouts and noise made by one generator. Real invoices are messier; handwriting and unusual formats are absent.
- Truth is known by construction, which is cleaner than real labelling. Planted problems are one per document and of 12 kinds chosen in advance.
- 300 documents per setting. Where a condition has few documents, its interval is wide; read the brackets, not the point values.
- One machine, one local model, one OCR engine. Speed will differ elsewhere.
- The checks are given a vendor list and earlier approved entries built from the fact sheet and the golden file. Real history is messier. See the harness notes in `docs/DECISIONS.md`.
- The model is run at temperature 0 with a fixed seed, so repeated passes are expected to be nearly identical. The spread between passes therefore says little about the spread between different documents, which is what the bootstrap measures.
- A person who wrote the system also wrote the test documents, so they are unseen but not blind.
- The fifth sealed set was run once, with the product's own settings and one pass, after the fourth round of fixes. It is now spent: any further change made after reading it would have to be tested on a new sealed set.

## Reading list

Documents worth opening by hand (not a failure count):

- **failed to process** (0): none
- **planted problem missed** (23): s5-crn-0036 (tax_mismatch, scan_heavy), s5-crn-0046 (amount_outlier, scan_heavy), s5-inv-0007 (tax_mismatch, scan_heavy), s5-inv-0010 (amount_outlier, phone_photo), s5-inv-0017 (injection_text, scan_heavy), s5-inv-0020 (injection_text, phone_photo), s5-inv-0021 (missing_invoice_number, clean_pdf), s5-inv-0023 (injection_text, scan_light), s5-inv-0030 (currency_mismatch, phone_photo), s5-inv-0043 (injection_text, scan_light), s5-inv-0061 (duplicate_invoice_number, scan_light), s5-inv-0084 (injection_text, scan_heavy), s5-inv-0085 (injection_text, scan_heavy), s5-inv-0107 (duplicate_invoice_number, phone_photo), s5-inv-0125 (injection_text, phone_photo), s5-inv-0140 (injection_text, scan_light), s5-inv-0149 (injection_text, clean_pdf), s5-inv-0157 (currency_mismatch, phone_photo), s5-inv-0158 (injection_text, clean_pdf), s5-rcp-0010 (injection_text, scan_light), s5-rcp-0011 (injection_text, scan_light), s5-rcp-0019 (injection_text, scan_light), s5-rcp-0049 (injection_text, scan_light)
- **false alarm on clean document** (53): s5-crn-0005 (TAX_MATCH; scan_heavy), s5-crn-0006 (LINE_MATH, VALUE_IN_DOCUMENT; scan_heavy), s5-crn-0008 (VALUE_IN_DOCUMENT; phone_photo), s5-crn-0009 (REQUIRED_FIELDS, TAX_MATCH; phone_photo), s5-crn-0016 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s5-crn-0019 (VALUE_IN_DOCUMENT; phone_photo), s5-crn-0024 (SUBTOTAL_MATCH; scan_light), s5-crn-0038 (VALUE_IN_DOCUMENT; phone_photo), s5-crn-0047 (SUBTOTAL_MATCH; phone_photo), s5-crn-0048 (VALUE_IN_DOCUMENT; phone_photo), s5-crn-0049 (VALUE_IN_DOCUMENT; phone_photo), s5-crn-0053 (SUBTOTAL_MATCH; scan_light), s5-crn-0055 (LINE_MATH, SUBTOTAL_MATCH, TAX_MATCH; scan_heavy), s5-crn-0056 (VALUE_IN_DOCUMENT; scan_heavy), s5-crn-0059 (LINE_MATH, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s5-inv-0015 (SUBTOTAL_MATCH; scan_light), s5-inv-0019 (TAX_MATCH, TOTAL_MATCH; phone_photo), s5-inv-0037 (LINE_MATH, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s5-inv-0039 (SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR; phone_photo), s5-inv-0040 (TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s5-inv-0046 (VALUE_IN_DOCUMENT; scan_heavy), s5-inv-0047 (VALUE_IN_DOCUMENT; scan_heavy), s5-inv-0049 (VALUE_IN_DOCUMENT; phone_photo), s5-inv-0050 (VALUE_IN_DOCUMENT; phone_photo), s5-inv-0057 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s5-inv-0060 (VALUE_IN_DOCUMENT; phone_photo), s5-inv-0065 (REQUIRED_FIELDS, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s5-inv-0066 (REQUIRED_FIELDS; phone_photo), s5-inv-0067 (REQUIRED_FIELDS; phone_photo), s5-inv-0074 (REQUIRED_FIELDS; scan_heavy), s5-inv-0075 (VALUE_IN_DOCUMENT; scan_heavy), s5-inv-0077 (REQUIRED_FIELDS, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s5-inv-0087 (REQUIRED_FIELDS; phone_photo), s5-inv-0088 (REQUIRED_FIELDS, TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s5-inv-0094 (REQUIRED_FIELDS; scan_heavy), s5-inv-0097 (REQUIRED_FIELDS; phone_photo), s5-inv-0098 (TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), s5-inv-0105 (REQUIRED_FIELDS, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s5-inv-0106 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; phone_photo), s5-inv-0108 (REQUIRED_FIELDS; phone_photo), s5-inv-0118 (LINE_MATH, REQUIRED_FIELDS, TOTAL_MATCH; phone_photo), s5-inv-0127 (REQUIRED_FIELDS, SUBTOTAL_MATCH; phone_photo), s5-inv-0134 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_heavy), s5-inv-0137 (LINE_MATH, REQUIRED_FIELDS; phone_photo), s5-inv-0164 (VALUE_IN_DOCUMENT; scan_heavy), s5-inv-0174 (VALUE_IN_DOCUMENT; scan_heavy), s5-rcp-0013 (SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s5-rcp-0016 (LINE_MATH; phone_photo), s5-rcp-0022 (VALUE_IN_DOCUMENT; scan_heavy), s5-rcp-0023 (VALUE_IN_DOCUMENT; scan_heavy), s5-rcp-0026 (VALUE_IN_DOCUMENT; phone_photo), s5-rcp-0033 (SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), s5-rcp-0043 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy)
- **header value invented** (12): s5-crn-0030, s5-crn-0031, s5-inv-0021, s5-inv-0070, s5-inv-0101, s5-inv-0144, s5-inv-0154, s5-inv-0164, s5-inv-0174, s5-rcp-0028, s5-rcp-0037, s5-rcp-0057
