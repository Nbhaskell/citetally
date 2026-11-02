# Development split: what the numbers say, and where they come from

Written after reading `eval_dev.md` (tuned split, 140 invented documents). Every number below is in that report or was counted from the same saved runs. Demo data: all vendors, invoices and amounts are invented.

## The short version

- **Clean digital PDFs work.** Header fields are 94.7% exact, line items 98.0% F1, and 99.0% of returned values are found on the page. The system still blocks 33.3% of clean documents (8 of 24), for reasons listed below.
- **Scans and photos do not work with the default path** (OCR text, then the text model). Header fields fall to 41.8% on heavy scans and 42.7% on phone photos, and strict line F1 is 2.5% and 0.0%. 2 of 35 heavy scans failed outright.
- **Reading the page image as well as the text fixes most of that.** On the same 69 documents, header fields rise from about 42% to 94.1% (heavy scans) and 97.8% (phone photos), and line F1 from 2.5% and 0.0% to 79.8% and 89.2%. The difference is real by the rule fixed in D-058 (larger than the spread between passes, bootstrap excludes zero). The cost is about 4 more seconds per page (12.2 s and 11.9 s against 8.7 s and 8.0 s).
- **But image reading has a price the headline hides.** Every one of the 49 clean documents in those two conditions fails `VALUE_IN_DOCUMENT`, because values read from the picture are checked against the OCR words, and the OCR words are the thing that was bad. That is why "clean documents with a blocking false alarm" gets worse (100% against 88%) while accuracy gets much better.
- **Planted-problem recall is 59.5% (44–73) overall and cannot be read on its own.** With 55 planted documents, each kind has 3 to 6 examples. Read the intervals.
- **Repeated passes agree.** Baseline passes 1 and 2 are identical on all four headline measures. This is expected at temperature 0 with a fixed seed, and it means the pass-to-pass interval says little about document-to-document variation.

## Where the errors come from

Counted from the baseline first pass unless stated.

### 1. OCR drops single-digit quantities (explains the low line scores)

On a clean PDF read as a scan (`forced_ocr`), header accuracy is unchanged (95.6% against 94.7%) but strict line F1 falls from 98.0% to 34.6%. The model returned no quantity for 48 of 101 lines, in every line of templates T06, T07 and T09 and in some lines of T01, T04 and T05. The words are on the page: for `inv-0059` the text layer has `Qty 1` and Tesseract's output has nothing in that column (69 words read against 72 in the layer). The model leaves the field empty rather than guess, which is the intended behaviour, and the strict line measure then counts the whole line as wrong. Counting a line right when its description and amount are right (added after the results were read, marked with an asterisk in the report) gives 94.1% for the same run. So most of the strict-F1 gap is this one OCR behaviour, not the model misreading prices.

The same effect is behind scan light (strict 25.9%, quantity ignored 72.6%). For heavy scans and photos the quantity is not the main problem (4.2% and 5.4% even when ignored): there the OCR text is itself too poor, and the model also splits and merges lines (141 and 158 lines returned for 99 and 102 real ones).

### 2. Image reading is accurate but cannot be grounded

With the page image as input the model reads the right values (98.0% line F1 ignoring quantity on both conditions). `SUBTOTAL_MATCH`, `TAX_MATCH` and `UNKNOWN_VENDOR` false alarms nearly disappear, and without `VALUE_IN_DOCUMENT` the false-alarm rate is 26.9% (heavy scans) and 4.3% (phone photos). But the grounding rule compares each value with the OCR words, so a correct value read from a badly OCR'd page is reported as not found. Two honest readings of that: the rule is working as designed (the system cannot show where the value is), and it also makes the image path unusable as it stands, since everything would need review. Choosing between "ground against a better text source", "ground against the image", and "accept image values with a different flag" is a design decision (D-049) and is not made here.

### 3. Clean PDFs: why a third are still blocked

Of 35 clean PDFs (24 without a planted problem):

- **Shortened vendor names (3 documents).** The model returned `Ledgerwell` for Ledgerwell Bookkeeping (`inv-0009`), `Sunbeam Print` for Sunbeam Print & Sign (`inv-0033`), and `Fuel & Convenience` for Tanager Fuel & Convenience (`rcp-0007`). The name is laid out across more than one line or column in these templates. `UNKNOWN_VENDOR` fires for a vendor that is on the list.
- **A currency symbol that is not printed (6 documents).** Templates T02 and T10 print amounts without a symbol; the model returns `$` as the currency, and `VALUE_IN_DOCUMENT` fails on that one field (`inv-0018`, `-0022`, `-0026`, `-0102`, `-0106`, `-0110`). This is the model adding something that is not on the page, and the grounding rule catching it. It is a false alarm only in the sense that the amounts are right.
- **One amount not found (1 document, `inv-0063`).** `$432.00` is not found on the page, and line math and subtotal fail with it.

### 4. Planted problems that were missed

Of 55 planted documents, 17 were missed (list in the report). The patterns that repeat:

- **`tax_mismatch`: 0 of 4 caught (0–56).** `TAX_MATCH` compares the stated tax with a per-line tax rate and passes with a note when no rate was read. On the misses no rate was read, so the check had nothing to hold the printed tax against. Separately, 12 of 501 lines have a dollar amount in the `tax_rate` field (the model put a printed tax amount where a rate belongs), so that field is not reliable.
- **`missing_invoice_number`: 1 of 4 caught (5–70).** On `inv-0076` the model returned the purchase order number (`PO-8190`) as the invoice number. The value is on the page, so grounding passes, and `REQUIRED_FIELDS` has nothing to complain about. This is a header-field confusion, and it is also in the 16 documents where a header value was invented.
- **`total_mismatch` flagged by the wrong check.** On `inv-0067` the page prints no subtotal; the model copied the total into the subtotal field, so `SUBTOTAL_MATCH` failed instead of `TOTAL_MATCH`. The document was still blocked, but the headline counts it as missed because it requires the expected check. This makes the headline slightly pessimistic.
- **Duplicates: 2 of 4 caught for `duplicate_invoice_number` and 2 of 4 for `duplicate_content`** (the table gives 50.0% for each, with 15–85% intervals). `crn-0006` copies `crn-0009`, a phone photo; the original has to be read well enough to be matched.
- **Injection text: 2 of 4 caught (15–85).** Four documents only; no conclusion.
- Recall for `amount_outlier` (4 of 4), `unknown_vendor` (3 of 3) and `due_before_entry` (1 of 1) rests on very few documents.

Planted documents also trigger other checks (`VALUE_IN_DOCUMENT` ×17, `SUBTOTAL_MATCH` ×15, `TOTAL_MATCH` ×13), mostly because the same reading errors that cause false alarms on clean documents also happen on them. This inflates "caught" a little for kinds whose expected check is one of those, and is one reason recall should be read next to the false-alarm rate, never alone. The text-and-image run shows it: it "catches" 34 points more planted documents and also has 12 points more false alarms.

### 5. Thinking mode (clean PDFs only, one pass)

On the 35 clean PDFs: header fields 94.7% (same), line F1 100.0% against 98.0%, planted problems caught 100.0% against 72.7% (11 documents), false alarms 33.3% (same), at 13.0 s per page against 5.4 s. With one pass a difference can never be called real under the rule in D-058, and the bootstrap interval for planted recall starts at zero. Treat this as a lead worth a second pass, not a result. It was not run on scans, where it would take much longer.

## What is frozen

The development numbers above are written down and will not be recalculated with a different method. Two columns were added after the first reading (line F1 ignoring quantity, false alarms without `VALUE_IN_DOCUMENT`); they explain the results and were not used to choose a setting. No change was made to the pipeline between the first run and this report: every run used the same code, apart from the harness itself.

## What this does not settle

- Whether any of the weaknesses above matter for a real business's documents, which are messier than these. The conclusion is limited to what the invented documents show.
- Whether fixing them (quantity recovery after OCR, vendor-name assembly, not accepting an unprinted currency symbol, reading the printed tax rate, grounding for image-read values) would work. None is tried here. Trying them would change the system, and the held-out set can be opened only once, so any fix made after seeing its numbers would need a new sealed set.
- The OCR engine comparison. It was done in Phase 3 (`ocr_bakeoff.json`) and not repeated.
