# Pilot: reviewing against typing by hand

Invented documents only, taken from the sealed set. One reviewer, the person who built the system.

## Targets

| Target | Result |
|---|---|
| 3. A document is finished in under half the time of typing it (median review / median typing under 0.5) | **0.26** (met) on 34 documents |
| 4. No wrong value approved without a recorded override | **2** of 34 approved entries had a wrong value and no override (not met); 3 had one with an override |

## Times

Median review 28 s, median typing 108 s; median of the per-document ratios 0.31.

| Condition | Documents | Review (median) | Typing (median) | Ratio |
|---|---|---|---|---|
| clean pdf | 10 | 22 s | 109 s | 0.20 |
| scan light | 10 | 16 s | 85 s | 0.19 |
| scan heavy | 4 | 28 s | 131 s | 0.21 |
| phone photo | 10 | 51 s | 127 s | 0.40 |

## Decisions and accuracy

- Of 40 documents: approved 34, rejected 6, set aside as duplicate 0; not reviewed: none; not typed: p01, p03, p04, p11, p12, p15.
- Approved entries with an accepted check (override): 16 of 34.
- Approved entries whose vendor, number, date, total or lines differ from the answer key: 5 (without an override: p23, p24; with one: p10, p20, p28).
- Approved entries with another header value different from the key (due date, PO number, currency, subtotal, tax, shipping, discount, type): 2.
- Documents typed with at least one difference from the key: 12 of 34.

## What this cannot tell you

- One reviewer, who built the system and knows how it fails; a new user would likely be slower.
- Review seconds are the time the review screen was open, including any pause. Typing seconds are from the first prompt to the last line.
- The documents are invented. Typing was done in a console helper, not a spreadsheet. Documents that copy another were left out, so duplicate handling is not part of this.
- 40 documents: read the per-condition rows as indications, not estimates.
