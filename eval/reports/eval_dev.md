# Evaluation: tuned split

Invented documents only (all vendors, invoices and amounts are made up). Numbers are from saved runs under `eval/runs/`; this report was made from them without calling the model.

## Provenance

|  |  |
|---|---|
| Commit | `1d41d50c05` (tree had changes) |
| Golden set | `eval\golden\citetally_v1.json` sha256 `d3225050fb55de0c…` |
| Model | ollama / qwen3:8b, temperature 0.0, seed 0 |
| Prompt version | extract-v3 |
| OCR | tesseract (tesseract v5.4.0.20240606) |
| Machine | Windows 11, Python 3.13.15 |
| Documents | 140 (tuned) |
| Passes per setting | baseline: 2, forced_ocr: 2, text_and_image: 2, thinking: 1 |
| Vendors on the list / earlier entries | 16 / 118 (20 repeated to reach the minimum history) |

## Headline numbers, baseline (first pass; shares pooled over all fields)

| Condition | Docs | Failed | Header fields exact | Money exact | Line F1 | Planted caught | Clean docs with a blocking false alarm | Values found on page |
|---|---|---|---|---|---|---|---|---|
| clean pdf | 35 | 0 | 94.7% (91–97) | 100.0% (96–100) | 98.0% | 72.7% (43–90) | 33.3% (18–53) | 99.0% |
| scan light | 36 | 0 | 92.1% (88–95) | 97.0% (91–99) | 25.9% | 63.6% (35–85) | 60.0% (41–77) | 94.8% |
| scan heavy | 35 | 2 | 41.8% (36–48) | 32.2% (23–42) | 2.5% | 44.4% (19–73) | 84.6% (66–94) | 89.2% |
| phone photo | 34 | 0 | 42.7% (36–49) | 50.0% (40–60) | 0.0% | 54.5% (28–79) | 91.3% (73–98) | 90.9% |
| all | 140 | 2 | 68.5% (65–71) | 70.3% (65–75) | 28.3% | 59.5% (44–73) | 67.3% (58–76) | 93.4% |

Percentages show the 95% Wilson interval in brackets. A document that failed counts every printed field as wrong.

## Header fields, baseline (all conditions)

| Field | Exact | Wrong | Missing | Invented |
|---|---|---|---|---|
| currency | 96.4% (92–98) | 3 | 2 | 0 |
| discount | 50.0% (27–73) | 6 | 1 | 2 |
| due_date | 81.0% (72–87) | 17 | 2 | 1 |
| entry_date | 77.1% (70–83) | 30 | 2 | 0 |
| invoice_number | 73.0% (64–80) | 30 | 3 | 7 |
| po_number | 79.4% (63–90) | 2 | 5 | 2 |
| shipping | 50.0% (27–73) | 5 | 2 | 2 |
| subtotal | 56.4% (48–65) | 35 | 20 | 5 |
| tax_total | 53.0% (42–63) | 34 | 5 | 0 |
| total | 68.6% (60–76) | 32 | 12 | 0 |
| vendor_name | 67.9% (60–75) | 43 | 2 | 0 |

## Planted problems caught, by check code

| Check | Caught |
|---|---|
| AMOUNT_OUTLIER | 100.0% (51–100) |
| CURRENCY_CHECK | 66.7% (21–94) |
| DATE_SANITY | 80.0% (38–96) |
| DUPLICATE_SUSPECT | 50.0% (22–78) |
| LINE_MATH | 50.0% (15–85) |
| REQUIRED_FIELDS | 25.0% (5–70) |
| SUSPICIOUS_TEXT | 50.0% (15–85) |
| TAX_MATCH | 0.0% (0–56) |
| TOTAL_MATCH | 75.0% (30–95) |
| UNKNOWN_VENDOR | 100.0% (44–100) |

By kind of problem:

| Planted kind | Caught |
|---|---|
| amount_outlier | 100.0% (51–100) |
| currency_mismatch | 66.7% (21–94) |
| due_before_entry | 100.0% (21–100) |
| duplicate_content | 50.0% (15–85) |
| duplicate_invoice_number | 50.0% (15–85) |
| future_date | 75.0% (30–95) |
| injection_text | 50.0% (15–85) |
| line_math | 50.0% (15–85) |
| missing_invoice_number | 25.0% (5–70) |
| tax_mismatch | 0.0% (0–56) |
| total_mismatch | 75.0% (30–95) |
| unknown_vendor | 100.0% (44–100) |

Other checks that also failed on planted documents: AMOUNT_OUTLIER ×1, DATE_SANITY ×2, LINE_MATH ×9, LOW_READ_QUALITY ×10, REQUIRED_FIELDS ×6, SUBTOTAL_MATCH ×15, TAX_MATCH ×4, TOTAL_MATCH ×13, UNKNOWN_VENDOR ×6, VALUE_IN_DOCUMENT ×17.

## False alarms on clean documents, by blocking check

| Check (of 98 clean documents) | Failing |
|---|---|
| REQUIRED_FIELDS | 19.4% (13–28) |
| VALUE_IN_DOCUMENT | 46.9% (37–57) |
| LINE_MATH | 20.4% (14–29) |
| SUBTOTAL_MATCH | 30.6% (22–40) |
| TAX_MATCH | 13.3% (8–21) |
| TOTAL_MATCH | 28.6% (21–38) |
| DUPLICATE_SUSPECT | 0.0% (0–4) |
| UNKNOWN_VENDOR | 31.6% (23–41) |

## Speed and size, baseline

| Condition | Median seconds per page | Input tokens (mean) | Output tokens (mean) |
|---|---|---|---|
| phone photo | 8.0 s | 773 | 390 |
| clean pdf | 5.4 s | 776 | 306 |
| scan light | 7.5 s | 776 | 304 |
| scan heavy | 8.7 s | 1038 | 385 |
| all | 7.5 s | 838 | 345 |

## Run-to-run spread

| Setting | Measure | Each pass | 95% t-interval |
|---|---|---|---|
| baseline | Header fields exact (share of printed fields read right) | 68.08%, 68.08% | ±0.00 points |
| baseline | Line items F1 | 32.22%, 32.22% | ±0.00 points |
| baseline | Planted problems caught (share of planted documents) | 59.52%, 59.52% | ±0.00 points |
| baseline | Clean documents with a blocking false alarm | 67.35%, 67.35% | ±0.00 points |
| forced_ocr | Header fields exact (share of printed fields read right) | 94.54%, 93.75% | ±5.04 points |
| forced_ocr | Line items F1 | 35.76%, 35.76% | ±0.00 points |
| forced_ocr | Planted problems caught (share of planted documents) | 60.00%, 60.00% | ±0.00 points |
| forced_ocr | Clean documents with a blocking false alarm | 25.00%, 25.00% | ±0.00 points |
| text_and_image | Header fields exact (share of printed fields read right) | 95.57%, 95.57% | ±0.00 points |
| text_and_image | Line items F1 | 85.34%, 85.34% | ±0.00 points |
| text_and_image | Planted problems caught (share of planted documents) | 84.21%, 84.21% | ±0.00 points |
| text_and_image | Clean documents with a blocking false alarm | 100.00%, 100.00% | ±0.00 points |

## Comparing settings with the baseline

A difference is called **real** only when it is larger than the spread between passes and a paired bootstrap over documents excludes zero. One of the two is **unclear**. Neither is **no difference found**: that is the size the test could not separate from noise, not proof of no effect.

### forced_ocr against baseline (35 documents, 2 pass(es))

| Measure | Difference | Bootstrap 95% | Pass spread | Verdict |
|---|---|---|---|---|
| Header fields exact (share of printed fields read right) | -0.30 points | -3.49 to +3.68 | ±5.04 | no difference found |
| Line items F1 | -59.95 points | -73.95 to -45.48 | ±0.00 | real (worse) |
| Planted problems caught (share of planted documents) | -12.73 points | -60.00 to +20.00 | ±0.00 | unclear |
| Clean documents with a blocking false alarm | -8.33 points | -29.17 to +12.50 | ±0.00 | unclear |

### text_and_image against baseline (69 documents, 2 pass(es))

| Measure | Difference | Bootstrap 95% | Pass spread | Verdict |
|---|---|---|---|---|
| Header fields exact (share of printed fields read right) | +53.54 points | +47.81 to +59.28 | ±0.00 | real (better) |
| Line items F1 | +83.41 points | +74.71 to +91.01 | ±0.00 | real (better) |
| Planted problems caught (share of planted documents) | +34.21 points | +10.53 to +52.63 | ±0.00 | real (better) |
| Clean documents with a blocking false alarm | +12.24 points | +4.08 to +22.45 | ±0.00 | real (worse) |

### thinking against baseline (35 documents, 1 pass(es))

| Measure | Difference | Bootstrap 95% | Pass spread | Verdict |
|---|---|---|---|---|
| Header fields exact (share of printed fields read right) | +0.45 points | -2.18 to +4.08 | – | no difference found |
| Line items F1 | +4.29 points | +0.00 to +11.43 | – | no difference found |
| Planted problems caught (share of planted documents) | +27.27 points | +0.00 to +50.00 | – | no difference found |
| Clean documents with a blocking false alarm | +0.00 points | -16.67 to +16.67 | – | no difference found |

## Settings side by side, by condition (first pass)

Each row is one setting on the documents it ran, so rows of the same condition use the same documents. The two columns marked with an asterisk were added after the first results were read, to explain them; they are context and were not used to choose anything.

| Condition | Setting | Docs | Header fields exact | Line F1 | Line F1, quantity ignored* | Planted caught | Clean false alarm | Clean false alarm without VALUE_IN_DOCUMENT* | Median s per page |
|---|---|---|---|---|---|---|---|---|---|
| clean pdf | baseline | 35 | 94.7% | 98.0% | 98.0% | 72.7% | 33.3% | 16.7% | 5.4 s |
| clean pdf | forced_ocr | 35 | 95.6% | 34.6% | 94.1% | 60.0% | 25.0% | 16.7% | 6.8 s |
| clean pdf | thinking | 35 | 94.7% | 100.0% | 100.0% | 100.0% | 33.3% | 8.3% | 13.0 s |
| scan light | baseline | 36 | 92.1% | 25.9% | 72.6% | 63.6% | 60.0% | 40.0% | 7.5 s |
| scan heavy | baseline | 35 | 41.8% | 2.5% | 4.2% | 44.4% | 84.6% | 84.6% | 8.7 s |
| scan heavy | text_and_image | 35 | 94.1% | 79.8% | 98.0% | 88.9% | 100.0% | 26.9% | 12.2 s |
| phone photo | baseline | 34 | 42.7% | 0.0% | 5.4% | 54.5% | 91.3% | 91.3% | 8.0 s |
| phone photo | text_and_image | 34 | 97.8% | 89.2% | 98.0% | 80.0% | 100.0% | 4.3% | 11.9 s |

## What this cannot tell you

- The documents are invented, with layouts and noise made by one generator. Real invoices are messier; handwriting and unusual formats are absent.
- Truth is known by construction, which is cleaner than real labelling. Planted problems are one per document and of 12 kinds chosen in advance.
- 140 documents per setting. Where a condition has few documents, its interval is wide; read the brackets, not the point values.
- One machine, one local model, one OCR engine. Speed will differ elsewhere.
- The checks are given a vendor list and earlier approved entries built from the fact sheet and the golden file. Real history is messier. See the harness notes in `docs/DECISIONS.md`.
- The model is run at temperature 0 with a fixed seed, so repeated passes are expected to be nearly identical. The spread between passes therefore says little about the spread between different documents, which is what the bootstrap measures.
- A person who wrote the system also wrote the test documents, so they are unseen but not blind.

## Reading list

Documents worth opening by hand (not a failure count):

- **failed to process** (2): crn-0004, rcp-0013
- **planted problem missed** (17): crn-0006 (duplicate_invoice_number, clean_pdf), crn-0013 (future_date, phone_photo), inv-0002 (tax_mismatch, scan_light), inv-0007 (injection_text, scan_heavy), inv-0015 (missing_invoice_number, scan_light), inv-0021 (injection_text, phone_photo), inv-0032 (tax_mismatch, phone_photo), inv-0036 (duplicate_invoice_number, phone_photo), inv-0040 (line_math, phone_photo), inv-0042 (missing_invoice_number, scan_light), inv-0067 (total_mismatch, clean_pdf), inv-0073 (tax_mismatch, scan_light), inv-0076 (missing_invoice_number, clean_pdf), inv-0087 (duplicate_content, scan_heavy), inv-0095 (currency_mismatch, scan_heavy), inv-0104 (duplicate_content, scan_heavy), inv-0112 (line_math, scan_heavy)
- **false alarm on clean document** (66): crn-0001 (SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), crn-0005 (TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), crn-0007 (SUBTOTAL_MATCH; scan_light), crn-0009 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), crn-0012 (REQUIRED_FIELDS, VALUE_IN_DOCUMENT; scan_heavy), inv-0003 (TOTAL_MATCH; scan_heavy), inv-0004 (LINE_MATH, SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0008 (LINE_MATH, TAX_MATCH, VALUE_IN_DOCUMENT; phone_photo), inv-0009 (UNKNOWN_VENDOR; clean_pdf), inv-0010 (SUBTOTAL_MATCH, TAX_MATCH, VALUE_IN_DOCUMENT; scan_light), inv-0011 (LINE_MATH, REQUIRED_FIELDS, SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0014 (SUBTOTAL_MATCH; scan_light), inv-0018 (VALUE_IN_DOCUMENT; clean_pdf), inv-0019 (LINE_MATH, VALUE_IN_DOCUMENT; scan_light), inv-0020 (REQUIRED_FIELDS, UNKNOWN_VENDOR; scan_heavy), inv-0022 (VALUE_IN_DOCUMENT; clean_pdf), inv-0023 (LINE_MATH, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; scan_light), inv-0024 (TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), inv-0025 (REQUIRED_FIELDS, SUBTOTAL_MATCH, TOTAL_MATCH; phone_photo), inv-0031 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR; scan_heavy), inv-0033 (UNKNOWN_VENDOR; clean_pdf), inv-0035 (LINE_MATH, SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), inv-0038 (LINE_MATH; scan_light), inv-0039 (SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0043 (VALUE_IN_DOCUMENT; scan_light), inv-0044 (REQUIRED_FIELDS, UNKNOWN_VENDOR; scan_heavy), inv-0048 (LINE_MATH, TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), inv-0049 (TOTAL_MATCH, UNKNOWN_VENDOR; phone_photo), inv-0051 (LINE_MATH, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; scan_light), inv-0055 (VALUE_IN_DOCUMENT; scan_light), inv-0056 (SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), inv-0058 (SUBTOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0061 (REQUIRED_FIELDS; scan_heavy), inv-0062 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0063 (LINE_MATH, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; clean_pdf), inv-0065 (REQUIRED_FIELDS, UNKNOWN_VENDOR; scan_heavy), inv-0066 (TOTAL_MATCH, UNKNOWN_VENDOR; phone_photo), inv-0069 (TOTAL_MATCH; scan_heavy), inv-0071 (LINE_MATH, TAX_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; phone_photo), inv-0075 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0077 (VALUE_IN_DOCUMENT; scan_light), inv-0078 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), inv-0079 (REQUIRED_FIELDS, TAX_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0082 (REQUIRED_FIELDS, SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; scan_heavy), inv-0083 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0090 (LINE_MATH; scan_light), inv-0091 (SUBTOTAL_MATCH; scan_heavy), inv-0092 (LINE_MATH, SUBTOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0096 (REQUIRED_FIELDS, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0100 (LINE_MATH, REQUIRED_FIELDS, SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0103 (VALUE_IN_DOCUMENT; scan_light), inv-0105 (LINE_MATH, SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0106 (VALUE_IN_DOCUMENT; clean_pdf), inv-0107 (SUBTOTAL_MATCH, VALUE_IN_DOCUMENT; scan_light), inv-0108 (REQUIRED_FIELDS, SUBTOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), inv-0109 (SUBTOTAL_MATCH, TAX_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), inv-0110 (VALUE_IN_DOCUMENT; clean_pdf), inv-0111 (VALUE_IN_DOCUMENT; scan_light), rcp-0001 (REQUIRED_FIELDS, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), rcp-0002 (REQUIRED_FIELDS, SUBTOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), rcp-0005 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), rcp-0007 (REQUIRED_FIELDS, UNKNOWN_VENDOR; clean_pdf), rcp-0009 (REQUIRED_FIELDS, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; scan_heavy), rcp-0010 (SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR, VALUE_IN_DOCUMENT; phone_photo), rcp-0012 (TOTAL_MATCH; scan_light), rcp-0014 (LINE_MATH, SUBTOTAL_MATCH, TOTAL_MATCH, UNKNOWN_VENDOR; phone_photo)
- **header value invented** (16): inv-0010, inv-0015, inv-0016, inv-0042, inv-0044, inv-0052, inv-0057, inv-0058, inv-0063, inv-0067, inv-0070, inv-0076, inv-0112, rcp-0001, rcp-0005, rcp-0010
