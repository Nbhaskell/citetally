# Implementation Plan: Citetally

Version 0.1. Build in phases. Each phase ends with an acceptance check; stop there and review before starting the next. Names come from `BACKEND_SCHEMA.md`, behavior from `TRD.md`. This plan is for a single developer working with Claude Code on Windows 11 (PowerShell), local-first.

Ground rules for every phase: tests first for plain code; fakes (`FakeOcr`, `FakeProvider`) so the test suite needs no model, OCR binary or network; small commits; decisions recorded in `docs/DECISIONS.md`; no real documents anywhere.

## Phase 0: Repository and tooling

Tasks
1. Create the repo `citetally` with the structure in `TRD.md` section 3, MIT license, `.gitignore` (data/, `*.db`, `.env`, eval/runs/), `.env.example`.
2. Python 3.13 environment with pinned dependencies; `pytest`, `ruff`, type checking.
3. FastAPI skeleton with `/api/status`; React + TypeScript + Vite skeleton; OpenAPI type generation.
4. `tools/check_env.py`: reports whether Tesseract and Ollama are reachable and which models are pulled, with Windows install hints. It must not fail the test suite.
5. GitHub Actions workflow: lint and tests only.
6. Fill in the Commands section of `CLAUDE.md`.

Acceptance: `pytest` passes with a trivial test; API answers `/api/status`; web app loads on port 5175 and shows the status; `check_env` prints a readable report.

## Phase 1: Synthetic data

Use the `synthetic-business-universe` skill. Truth is known by construction.

Tasks
1. Define about 15 invented vendors with variants of their names (for aliases), default categories, typical amounts and currencies. All fictional: invented names, 555-01xx phones, example.com emails.
2. Build at least 12 **template families** (layout styles) with `reportlab`: single-table invoice, two-column header, receipt narrow roll, credit note, invoice with shipping and discount, tax per line, no subtotal printed, and so on. Vary fonts, logo blocks, column order, date and number formats.
3. Generate documents with the truth recorded as printed text plus parsed values.
4. Degradation tool producing four conditions: `clean_pdf`, `scan_light`, `scan_heavy` (rotation, blur, noise, contrast loss, shadows), `phone_photo` (perspective, uneven light, background).
5. Planted problems (see `TRD.md` section 12), recorded with expected check codes. About a quarter of documents carry a problem; planted duplicates include same number and same content under a new number.
6. Golden-set builder writes `eval/golden/citetally_v1.json` (≥150 documents; ~200 recommended). **Hold out whole template families**, at least a third, and keep their documents in a separate `heldout` split that is not opened until Phase 8.
7. A demo loader that loads a small labelled demo set (about 12 documents) for the UI.

Acceptance: generation is deterministic from a seed; a script prints counts by condition, family, split and planted kind; a sample of documents has been looked at by eye (open a few of each condition); the golden file validates against its schema; held-out families do not appear in any dev document.

## Phase 2: Data layer

Tasks
1. SQL migrations for every table in `BACKEND_SCHEMA.md`, with `CHECK` constraints for the enums; `python -m citetally.db migrate`; seed categories.
2. Pydantic models with enums defined once; a test that keeps code enums and the database `CHECK` constraints in step.
3. Repository functions and the state machine with every transition in the schema (and tests for each illegal transition).
4. `audit_events` helper and a test that no document text, vendor name, invoice number or amount appears in log output.

Acceptance: migrations apply from an empty database and are idempotent; state machine tests pass; enum-sync test passes.

## Phase 3: Ingest and read

Tasks
1. `money.py` and `dates.py` with exhaustive unit tests, including ambiguous formats, thousands separators, parentheses negatives, currency symbols, and round-half-up. No floats.
2. Ingest: magic-byte type detection, size, page and pixel limits, hashing, storage by hash, page rendering, duplicate-by-hash.
3. Text-layer reader and layout-preserving text builder.
4. Pre-processing (orientation, deskew, denoise, contrast).
5. `OcrEngine` interface, `TesseractOcr`, `FakeOcr`.
6. Card-like number masking with Luhn check.
7. Security tests (oversized and malformed files, wrong extension, hostile filenames).
8. **OCR bake-off:** run Tesseract and at least one alternative on the synthetic scans; compare word accuracy, number accuracy, and speed per page on the dev split only. Record the choice and the numbers in `docs/DECISIONS.md`.

Acceptance: every golden dev document reads without crashing; a small report shows word-level accuracy by condition; security tests pass.

## Phase 4: Extraction and grounding

Tasks
1. `ModelProvider`, `OllamaProvider`, `FakeProvider`; recorded-reply contract test.
2. Extraction prompt `extract-v1` and schema; retries; token recording; the data-block delimiting of document text.
3. Grounding: parse, locate, evidence rows, numeric fallback, threshold setting.
4. Vendor matching and category suggestion.
5. Pipeline orchestration with idempotent stage re-runs and failure states.
6. **Optional vision experiment:** with a local vision model, compare `text_only` against `text_and_image` on the dev split's `scan_heavy` and `phone_photo` documents. Enable only if it clearly helps and fits the hardware. Record the result either way.

Acceptance: on the dev split, a first measurement of header field accuracy and line item accuracy per condition; grounding coverage reported; the pipeline handles a model outage and an invalid JSON reply with the right statuses.

## Phase 5: Checks, review logic and API

Tasks
1. All 14 checks as pure functions with unit tests for pass, fail and edge cases (rounding, missing subtotal, no tax rate, credit notes, thin history for outliers, ambiguous dates).
2. Blocking versus non-blocking behavior; override rules; overrides cleared on edit; re-run on edit.
3. Duplicate logic by invoice number and by content.
4. Injection-text detection and adversarial tests.
5. API routes from `TRD.md` section 7 with consistent errors and request ids; background worker; status endpoint.
6. Review timing recorded as `review_seconds`.

Acceptance: API tests cover every route and every decision; approving with an unresolved blocking check is refused; every status transition works through the API.

## Phase 6: Export

Tasks
1. `lines_csv` and `entries_csv` profiles; credit notes negative; amounts as decimal strings from minor units.
2. CSV formula-injection neutralization and RFC 4180 quoting, with tests using hostile strings.
3. Already-exported guard and export history, hashes, counts.
4. Round-trip test: export, parse with a CSV reader, compare to the database to the cent.

Acceptance: a spreadsheet opens the file with no formulas executed from document text; totals in the CSV equal totals in the database.

## Phase 7: UI

Use `frontend-design` and `ai-ui-patterns`. Follow `UI_UX_DESIGN_BRIEF.md`.

Order: shared components and money cell → Inbox → Review (page with evidence boxes, fields, line arithmetic, checks panel, action bar, dialogs) → Vendors → Exports → Insights → Settings → keyboard shortcuts → responsive pass at 360 px.

Acceptance: a person who has never seen the app can upload a demo file, fix a wrong value, resolve a blocking check, approve, and export in under three minutes with no explanation; accessibility pass (keyboard-only run, screen reader sanity check, contrast); component tests for all states.

## Phase 8: Evaluation

Use the `qa-eval-harness` skill.

Tasks
1. Runner (produces results per document) and scorer (computes metrics) as separate programs; each run records commit, settings, provider, model, OCR engine, prompt versions and golden-set hash.
2. Metrics from `TRD.md` section 12, reported per condition and per check code.
3. Dev-split ablations: text layer versus forced OCR; OCR engine; text-only versus text-and-image if enabled; thinking on versus off. Repeat runs to measure spread.
4. **Held-out run, once**, on unseen template families after the dev numbers are frozen. Report as it comes out.
5. Error analysis: read the failures; group them (misread digit, wrong line split, missed planted problem, false alarm) and show examples.
6. Written "what this cannot tell you".

Acceptance: a report in `eval/reports/` with tables, the ablations, the held-out numbers, and the limits; numbers in the README match the report exactly.

## Phase 9: Hardening

Tasks
1. Re-run the security tests; fuzz the ingest with malformed files; check parsing timeouts and worker isolation.
2. Dependency audit and license check (no AGPL).
3. Log review: confirm no document content appears.
4. Failure drills: kill the model mid-run, remove Tesseract, fill the disk, corrupt a page, restart mid-queue; verify statuses and retries.
5. Performance: measure median time per page by condition on the target machine.

Acceptance: the drills behave as documented; no high-severity findings open.

## Phase 10: Documentation and publish

Use `project-case-study-readme` and `pre-publish-checklist`.

Tasks
1. README with the problem, the principle (model reads, code checks), screenshots of the review screen, the evaluation table, the limits, and how to run it locally (Windows first).
2. Architecture diagram and a short walkthrough GIF.
3. Complete `docs/DECISIONS.md`.
4. Run the pre-publish checklist: secrets scan across history, no real data, synthetic labelling, license, claims versus evidence.

Acceptance: a stranger can clone, run the demo, and reproduce the dev evaluation from the README.

## Stretch (after v1)

1. **`HostedProvider`** implementing `ModelProvider`, behind `CITETALLY_ALLOW_HOSTED`, with the hosted banner, per-document token cost, and a side-by-side report (accuracy by condition, time, cost per document) against the local model. Re-validate prompts on the golden set; do not assume they transfer.
2. Email intake (a watched folder first; a mailbox connector later, read-only, with drafts only for any outgoing mail).
3. Export profiles for specific accounting software, each after reading that software's current import specification.
4. Bank statement reconciliation.
5. Purchase order matching.
6. Adapter to reuse `citecheck`'s figure checking for the grounding step.
7. Multi-invoice PDF splitting.

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Local OCR too weak on `phone_photo` | High | Pre-processing; report honestly by condition; optional vision experiment; hosted comparison later |
| Local model misreads or "repairs" numbers | Medium | Copy-as-printed prompt; grounding rejects values not on the page; arithmetic in code |
| Local model slow on this hardware | Medium | Thinking off; one document at a time; measure and report time |
| Overfitting to the synthetic layouts | High | Held-out template families, run once; report the limits |
| Scope creep into accounting features | Medium | Non-goals in `PRD.md`; stretch list is after v1 |
| OCR dependency painful on Windows | Medium | `check_env` script with clear steps; `FakeOcr` keeps tests independent |
| AGPL dependency sneaks in | Low | License check in Phase 0 and Phase 9 |
| Prompt injection in documents | Medium | Untrusted-data delimiting; code-only decisions; `SUSPICIOUS_TEXT`; adversarial golden items |
| Port clash with sister projects | Low | Fixed ports: 8200 and 5175 |

## Definition of done (v1)

- All MVP requirements in `PRD.md` implemented and tested.
- Full pipeline runs locally on the demo set and on the golden set.
- Evaluation report complete, with held-out numbers, ablations and limits.
- No automatic payment, posting or sending of any kind; export is a downloaded CSV.
- Security, hardening and pre-publish checks complete.
- README and case study match the measured results.

## First prompt for Claude Code

> Read `CLAUDE.md`, then the documents in `docs/`. Do Phase 0 only from `docs/IMPLEMENTATION_PLAN.md`. Ask me before installing anything outside the project. When Phase 0's acceptance check passes, fill in the Commands section of `CLAUDE.md`, summarize what you did, and stop.
