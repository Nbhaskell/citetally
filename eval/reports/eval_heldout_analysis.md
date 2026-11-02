# Held-out split: one run, reported as it came out

Demo data: all vendors, invoices and amounts are invented. This is the single run of the held-out split (70 documents from template families T11 to T15, none used while building or tuning). It used the baseline setting, unchanged since the development report (commit f3353cf, clean tree). Full tables are in `eval_heldout.md`. The held-out split is now spent: it was opened once, and any change made after reading it needs a new sealed set to test.

## Development against held-out (baseline, first pass)

Shares are pooled over all fields or documents, with the 95% interval in brackets, as in the two reports.

| Measure | Development (140) | Held-out (70) |
|---|---|---|
| Header fields exact | 68.5% (65–71) | 50.7% (46–55) |
| Money exact | 70.3% (65–75) | 56.2% (49–63) |
| Line F1 | 28.3% | 23.2% |
| Planted problems caught | 59.5% (44–73) | 61.5% (36–82) |
| Clean documents with a blocking false alarm | 67.3% (58–76) | 80.7% (69–89) |
| Values found on page | 93.4% | 92.9% |
| Documents that failed | 2 | 1 |

Header fields exact by condition:

| Condition | Development | Held-out |
|---|---|---|
| clean pdf | 94.7% (91–97) | 97.3% (92–99) |
| scan light | 92.1% (88–95) | 80.0% (72–86) |
| scan heavy | 41.8% (36–48) | 10.7% (6–18) |
| phone photo | 42.7% (36–49) | 20.7% (14–29) |

## What to take from it

- **Clean PDFs held up.** Header fields are 97.3% exact and line items 88.7% F1 on template families the system had never seen.
- **Scans and photos are worse than in development**, and development was already poor there. Heavy scans read 10.7% of header fields right and phone photos 20.7%; strict line F1 is 0.0% and 1.8%. The default OCR-then-text path does not read degraded documents. This is the number to quote, not the development one.
- **Why the gap, I do not know.** Nothing was tuned on the development split, so it is not tuning leakage. Candidates are different layouts, noisier scans in the held-out sample, and the small samples (17 or 18 documents per condition). None was tested; the report does not separate them.
- **The text-and-image setting has no held-out number.** The split can be opened once, so only the shipped default was run. The development evidence for image reading (header fields 94.1% on heavy scans and 97.8% on phone photos) stands as a development result only.
- **False alarms are high everywhere**: 8 of 12 clean PDFs were blocked. Reading those 8 (reading only, nothing changed): 4 receipts of template T13 where the model returned `$` as the currency although none is printed (the same pattern as in development), 3 invoices where a tax rate or a vendor name the model returned was not found as written on the page (for example a rate returned as `7%`), and one with a due date not found. Some also fail `REQUIRED_FIELDS`. So the clean-PDF false alarms are the same kinds as in development, not a new failure.
- **"Planted problems caught" is 8 of 13 documents and cannot be read on its own.** Heavy scans show 100.0% (21–100), which is one planted document, and almost every check fails on them anyway (94.1% false alarm). Per kind there are one to three documents. `tax_mismatch` (0 caught), `currency_mismatch` (0) and `duplicate_content` (0) were missed again; the intervals reach 66% to 79%, so the test could not rule out a decent rate.

## What this cannot tell you

Everything in "What this cannot tell you" in `eval_heldout.md` applies, plus: one pass of one setting, so no spread between passes can be shown for it; 70 documents; and a gap of this size between development and held-out is exactly what a small, differently laid-out sample can produce, so the safest reading is "weak on degraded documents, fine on clean PDFs", not the second decimal.
