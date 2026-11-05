# Pilot: reviewing against typing by hand

Invented documents only, taken from the second sealed set. One reviewer, the person who built the system.

## Targets

| Target | Result |
|---|---|
| 3. A document is finished in under half the time of typing it (median review / median typing under 0.5) | **0.44** (met) on 36 documents |
| 4. No wrong value approved without a recorded override | **1** of 36 approved entries had a wrong value and no override (not met); 0 had one with an override |

## Times

Median review 39 s, median typing 89 s; median of the per-document ratios 0.48.

| Condition | Documents | Review (median) | Typing (median) | Ratio |
|---|---|---|---|---|
| clean pdf | 10 | 57 s | 93 s | 0.61 |
| scan light | 10 | 25 s | 81 s | 0.31 |
| scan heavy | 7 | 63 s | 87 s | 0.72 |
| phone photo | 9 | 96 s | 95 s | 1.01 |

## Decisions and accuracy

- Of 40 documents: approved 36, rejected 4, set aside as duplicate 0; not reviewed: none; not typed: p05, p10, p11, p32.
- Approved entries with an accepted check (override): 13 of 36.
- Approved entries whose vendor, number, date, total or lines differ from the answer key: 1 (without an override: p09; with one: none).
- Approved entries with another header value different from the key (due date, PO number, currency, subtotal, tax, shipping, discount, type): 2.
- Documents typed with at least one difference from the key: 15 of 36.

## What this cannot tell you

- One reviewer, who built the system and knows how it fails; a new user would likely be slower.
- Review seconds are the time the review screen was open, including any pause. Typing seconds are from the first prompt to the last line.
- The documents are invented. Typing was done in a console helper, not a spreadsheet. Documents that copy another were left out, so duplicate handling is not part of this.
- 40 documents: read the per-condition rows as indications, not estimates.
