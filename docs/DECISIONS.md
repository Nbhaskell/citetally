# Decisions

Decisions the planning documents do not cover. Each entry says what was chosen and why. Newest last.

## Phase 0

### D-001. Planning documents live in `docs/`
`CLAUDE.md` and `docs/TRD.md` section 3 both say the planning documents are in `docs/`, but they were delivered in the repository root. Moved them into `docs/` before the first commit.

### D-002. Directories and sub-packages are created, empty module files are not
`docs/TRD.md` section 3 lists every module. Phase 0 creates the directories (`db/migrations`, `db/seed`, `eval`, `tools`, `tests`, `web`) and the sub-packages (`citetally/reading`, `citetally/checks`, `citetally/providers`). Individual module files (`db.py`, `money.py` and so on) are created in the phase that implements them, so there are no empty stubs to mislead a reader.

### D-003. Line endings: LF
`.gitattributes` sets `* text=auto eol=lf` so Windows checkouts and the Linux CI runner agree and ruff's formatter does not report line-ending differences.

### D-004. Python dependencies are pinned in two requirements files
`requirements.txt` holds runtime dependencies and `requirements-dev.txt` adds test and lint tools (`-r requirements.txt` plus pytest, ruff, mypy, httpx2). Both list every package, including transitive ones, at exact versions (a `pip freeze` of the virtual environment), so installs are reproducible. No extra lock tool. Phase 0 installs only what Phase 0 uses; later phases add `pdfplumber`, `pypdfium2`, Pillow, OpenCV, `reportlab` and so on, each after a license check.

Type checking is `mypy --strict` with the pydantic plugin. Lint and format are `ruff`, which skips `docs/` and `web/` because recent ruff versions also format Markdown code blocks and the planning documents should not be rewritten by a formatter.

FastAPI's test client needs an HTTP client library. Starlette now deprecates `httpx` there in favor of `httpx2` (BSD-3-Clause), so the dev requirements use `httpx2`. This also avoids `certifi` (MPL-2.0).

### D-005. License check of the Python dependencies
Every installed package was checked. All are MIT, BSD, Apache-2.0 or PSF, with one exception: `pathspec` (MPL-2.0, weak file-level copyleft), pulled in by `mypy`. It is development-only, unmodified and not redistributed, so it does not affect the MIT license of this repository. No AGPL or GPL. Accepted in D-011.

### D-006. Settings use the names in TRD section 8, in one class, with `.env` optional
`citetally/config.py` has a single `Settings` class (pydantic-settings). Each field is bound to its documented variable name (`CITETALLY_*`, plus `OLLAMA_URL` and `TESSERACT_CMD`), empty values fall back to defaults so `.env.example` can ship with blank entries, and unknown variables are ignored. Phase 0 includes only the settings that exist so far. `CITETALLY_MODEL_PROVIDER=hosted` without `CITETALLY_ALLOW_HOSTED=true` fails at startup (TRD section 6).

The server's bind address is a constant, not a setting: `python -m citetally` always binds to `127.0.0.1`, because v1 has no authentication. The app is built by `create_app(settings)`, not a module-level global, so tests can build one without reading a local `.env`.

### D-007. `/api/status` in Phase 0 reports only what exists
TRD section 7 lists the fields (provider, model, OCR engine, database health, hosted-mode flag, synthetic-data flag) and section 10 adds last model call, OCR availability and queue depth. Phase 0 returns the configured values and returns `null` for database health, OCR availability, queue depth and last model call, because those parts are built in Phases 2 to 5. `null` means "not reported yet", never "healthy". Field names are `app`, `version`, `model_provider`, `text_model`, `vision_model`, `ocr_engine`, `hosted_mode`, `synthetic_data`, `database_ok`, `ocr_available`, `queue_depth` and `last_model_call_at`. `docs/BACKEND_SCHEMA.md` does not name them, so confirm them when Phase 5 builds the real endpoint.

### D-008. Web app setup
React 19, Vite 8, TypeScript, Vitest with Testing Library and jsdom, and ESLint with typescript-eslint, all at exact versions in `web/package.json` with `package-lock.json` committed.

- **TypeScript 5.9.3, not 7.x.** The newest TypeScript is outside the supported range of `typescript-eslint` (below 6.1) and `openapi-typescript` (5.x). 5.9.3 satisfies both.
- **Dev proxy, no CORS.** Vite serves on `127.0.0.1:5175` (strict port) and proxies `/api` to `127.0.0.1:8200`, so the browser sees one origin and the API needs no CORS settings.
- **Generated types.** `python -m tools.export_openapi` writes `web/openapi.json` from the FastAPI app, and `npm run gen:api` in `web/` turns it into `web/src/api/schema.d.ts`. Both files are committed. A pytest test fails if `openapi.json` is out of date, and CI fails if `schema.d.ts` is out of date with `openapi.json`.
- **Licenses.** All npm packages are MIT, ISC, BSD, Apache-2.0 or similar, with two build-time exceptions that are not shipped: `lightningcss` (MPL-2.0, a Vite dependency) and `caniuse-lite` (CC-BY-4.0, browser-support data). No AGPL or GPL. Accepted in D-011.
- The status page renders every value as text. The hosted-mode banner is already wired to `hosted_mode`; its wording ("a hosted provider") becomes the provider's name when hosted mode exists.

### D-009. `tools/check_env.py` design
Standard library only, so it runs before the virtual environment exists. It reads `.env` (real environment variables win) and reports Python 3.13, Node.js, Tesseract (including the `eng` language data), Ollama reachability, which models are pulled, and whether the configured text model (and vision model, if set) is among them. Tesseract is looked up from `TESSERACT_CMD`, then `PATH`, then the default Windows install folders. It prints Windows install hints (`winget install ...`) but never installs anything. It exits 0 whatever it finds; `--strict` exits 1 if anything is missing. Machine access goes through an injected `Probes` object, so its tests need no Tesseract, no Ollama and no network. It accepts only `http://` or `https://` for `OLLAMA_URL`. Node.js is included because the web app needs it, which goes slightly beyond the plan's "Tesseract and Ollama".

### D-010. CI is tests and lint only
`.github/workflows/ci.yml` has two jobs on `ubuntu-latest` (Python 3.13 and Node 24) that run on pushes to `main` and on pull requests, with read-only permissions. The Python job runs `ruff check`, `ruff format --check`, `mypy`, `pytest` the personal-information check (D-013) and the secret scan (D-014). The web job runs `npm ci`, ESLint, `tsc` and Vitest, then regenerates the API types to confirm `web/src/api/schema.d.ts` matches `web/openapi.json`. Nothing needs a model, an OCR binary or network access, and nothing deploys. Action versions are the latest majors at the time of writing (checkout v7, setup-python v7, setup-node v7). First run on GitHub (2026-10-30, commit `bab47f7`) passed in 26 seconds.

### D-011. MPL-2.0 development tools accepted
The owner accepted the weak-copyleft development-only tools flagged in D-005 (`pathspec`, via `mypy`) and D-008 (`lightningcss`, via Vite), and the CC-BY-4.0 `caniuse-lite` data. Reason: file-level copyleft, unmodified, build and test time only, not part of the shipped code. This is a narrow exception to `CLAUDE.md` rule 10. AGPL and GPL remain banned, and any new copyleft dependency, or any MPL dependency used at runtime, still needs a fresh decision.

### D-012. `CLAUDE.md` is not tracked
`citedesk`, `rag-project` and `citewise-markets` all git-ignore `CLAUDE.md` and `CLAUDE.local.md`, and `citecheck` tracks no assistant-instruction file. `CLAUDE.md` is read from the local working folder, so GitHub and CI do not need it. It was committed by mistake in the first commit; it is now untracked and listed in `.gitignore`, and the file stays on disk. The planning documents in `docs/` stay tracked, as in `citedesk`. Earlier commits on the private remote still contain the file. Its content holds no secrets, and the history check belongs in the `pre-publish-checklist` run before the repository goes public.

### D-013. Personal information is blocked by a hook and by CI
`tools/check_personal_info.py` (standard library only, tested without git) flags what should never be published: local user-profile paths, email addresses and phone numbers that are not invented ones (`example.com` addresses, GitHub noreply addresses and 555-01xx numbers pass), wording that describes the owner (experience, budget), and assistant-instruction files. With `--staged` it also refuses a commit whose author email is not a GitHub noreply address. Findings print the file, line and label, never the matched text, so CI logs do not repeat it. The patterns are generic, so the tracked checker holds no personal data itself.

- **Hook.** `.githooks/pre-commit` runs `--staged`. Turn it on once per clone with `git config core.hooksPath .githooks`. It uses no extra tool, unlike the `pre-commit` framework `citedesk` uses for its secret scan.
- **CI.** The Python job runs `--all` over every tracked file.
- **Not covered.** This is a pattern check. It does not catch a name or fact it has no pattern for, and it is not a secret scanner. Secret scanning is a separate check (D-014).

### D-014. Secret scan: gitleaks, a pinned copy kept inside the project
`citedesk` runs gitleaks through the `pre-commit` framework. That framework installs its tools (and a Go toolchain) into a cache outside the project and refuses to install while `core.hooksPath` is set, which D-013 uses. So this project runs the same gitleaks (v8.30.1, MIT) another way: `tools/secret_scan.py --fetch` downloads the release for the current platform into `.tools/` (git-ignored) and checks it against SHA-256 values pinned in the script, so nothing is installed system-wide and a tampered download is refused.

- **Hook.** `.githooks/pre-commit` runs the personal-information check, then `--staged`. A missing gitleaks fails the commit with the fetch command, because a guard that silently skips is not a guard.
- **CI.** The Python job fetches the same pinned copy and scans the whole history (`--history`, which needs `fetch-depth: 0`), which is also the history scan `docs/TRD.md` section 9 asks for before publishing.
- **Rules.** `.gitleaks.toml` extends gitleaks' built-in ruleset, as in `citedesk`, with no allowlist. Add an allowlist entry only with a written reason.
- **Output.** Scans use `--redact`, so a found secret is never printed.
- **Checked.** A history scan of the first 11 commits found nothing, and a commit containing a fake token-shaped string was refused.
- **Updating.** Change `VERSION` and the pinned checksums together, from the release's checksums file.

## Phase 1

### D-015. The invented business is citedesk's plumbing company, copied as a snapshot
The demo business is **Kestrel Hollow Plumbing**, the same invented residential plumbing company as the `citedesk` project, so the two projects tell one story (a plumbing company's customer inquiries in one, its vendor invoices and receipts in the other). The identity (name, street, town, phone, email, currency, parts sales tax of 7%) was copied from `citedesk`'s `universe/facts.json` at its commit `7389323` into this project's own `universe/facts.json`. Nothing here reads, imports or links to the other project, so neither has to be finished for the other to work; if `citedesk`'s business changes, update this file by hand. `citedesk` gives no state or ZIP code, so the bill-to address uses an invented state and an unassigned ZIP (`00171`).

The 16 vendors are invented for a plumbing business: pipe and fittings and water-heater wholesalers (the two `SUPPLIES` vendors), uniform service, electric and water utilities, tool repair, insurance, field-service and pipe-camera software (one billed in euros with 19% VAT), bookkeeping, fuel and a deli (receipts), van service, printing, a local directory, and the county building department for permits. Vendor towns reuse the service-area names from `citedesk`'s fact sheet. Phones are 555-01xx, emails are at `example.com`, and ZIP codes use the unassigned `00xxx` range. Tests (`tests/test_synthetic_facts.py`) enforce this.

**Documents that still describe a pet business.** `docs/BACKEND_SCHEMA.md` has the category label "Food and treats" (section 1) and two sample JSON blocks that use "Northfield Pet Supply Co." and "Kibble" (sections on extraction and the golden item). They are labels and illustrations, not requirements, so they are left as written for now. Category codes do not change. The seed category labels are set in Phase 2 (`db/seed/categories.json`); retheme the sample blocks and the label then, or earlier if the owner prefers.

### D-016. Test-data tooling and its dependencies
Documents are made by code under `tools/synthetic/` from `universe/facts.json`. New development-only packages, pinned in `requirements-dev.txt`: `reportlab` (BSD, PDF rendering), `pillow` (MIT-CMU, a permissive license; image degradation) and `numpy` (BSD-3-Clause with permissive bundled parts; noise and lighting). All three passed the license check. They move to the runtime requirements when Phase 3 uses Pillow and NumPy in the product.

**OpenCV is not used in Phase 1.** `docs/TRD.md` lists OpenCV for pre-processing, but its pip wheels bundle FFmpeg libraries that are, as far as I know, LGPL, which `CLAUDE.md` rule 10 treats as copyleft. Degradation (blur, noise, rotation, perspective, uneven light) is done with Pillow and NumPy instead. Check the OpenCV license position again before Phase 3 adds it.

### D-017. Truth is computed by the generator, not by the product's code
The generator has its own small exact-decimal arithmetic (`Decimal`, round half up) and its own date formatting, and does not import `citetally.money` or `citetally.dates` (Phase 3). If it did, a bug in the product's arithmetic would also corrupt the answer key and the evaluation could not see it.

### D-018. Printed values: unambiguous dates, several money styles, unlisted vendors
Generated documents print dates only as `2026-03-04`, `March 4, 2026`, `4 Mar 2026` or `Mar 4, 2026`. Numeric slash dates (`03/04/2026`) are never generated, because they can be read two ways and the answer key would have to guess which was meant; the `AMBIGUOUS_FORMAT` check is covered by unit tests on the date code in Phase 3 instead, not by the golden set. Money prints in six styles (`$1,234.56`, `1,234.56`, `USD 1,234.56`, `$1234.56`, `($45.00)` for credit notes, and the European `1.234,56 €` used by the euro vendor). `facts.json` also holds three `unlisted_vendors` that are not in the vendor list, to make `UNKNOWN_VENDOR` documents.

### D-019. `CURRENCY_CHECK` wording is ambiguous in the docs
`TRD.md` section 4.6 and `BACKEND_SCHEMA.md` say the check fires when the currency "differs from the default **or** from the vendor's default". Read literally, every euro invoice from the euro vendor would fire it, even though euros are that vendor's usual currency. The golden set therefore marks `CURRENCY_CHECK` as expected only for planted `currency_mismatch` documents (an invoice in a currency other than the vendor's usual), and does not count it as a false alarm on the euro vendor's own documents. Decide the exact rule when Phase 5 builds the check, and tell the owner which reading was chosen.

### D-020. Fifteen template families, ten tuned and five held out
`tools/synthetic/families.py` defines 15 layouts (T01 to T15) drawn by six renderer kinds. Ten families (T01 to T10) are for building and tuning: single-table, two-column header, narrow receipt roll, credit note, shipping and discount, tax on every line, no subtotal printed, stacked utility bill, plain letter style and a dense repair order. Five (T11 to T15) are held out: a sidebar invoice, a billing statement with a summary box, a full-page point-of-sale receipt, a landscape invoice and a credit note in the statement layout. Three renderer kinds (sidebar, statement, pos_page) are used only by held-out families, so the held-out split tests structures the tuned set never shows, not just recoloured ones. Every vendor appears in the tuned set. Tests check every printed value in the answer key against the PDF text layer for all 15 families, so the key cannot drift from what is drawn.

Held-out documents also get a different kind of damage (`profile="heldout"` in `degrade.py`): streaks and JPEG artefacts on light scans; larger skew, creases, speckle and fax-style black and white on heavy scans; stronger perspective, a hard shadow and motion blur on phone photos.

**Two documents disagree about when the held-out set is made.** `IMPLEMENTATION_PLAN.md` Phase 1 task 6 builds the held-out split now, in the golden-set builder. `TRD.md` section 12 says it is generated *after the first prototype exists*, with new layouts and new degradations. Followed the plan: the split exists, but it is sealed (`load_golden` refuses to return it without `unseal_heldout=True`, and the counts report reads only a separate summary file). Its layouts and damage are already different from the tuned set. If the TRD's stricter reading is wanted, regenerate the held-out families with a new seed after the Phase 4 prototype and record the new seed here.

### D-021. The golden item has a few more fields than `BACKEND_SCHEMA.md` shows
Added to the item shape: `source_kind` and `vendor_id`; in `truth`, `po_number`, `shipping_minor`, `discount_minor` and a `printed` block with the exact text printed for each header field; per line, `tax_minor` (when the layout shows tax per line) and a `printed` block. A value is `null` when the document does not print it (for example the subtotal on a "no subtotal printed" layout). The file begins with a `header` (seed, generator version, SHA-256 of `universe/facts.json`, digest of all generated files, counts). `eval/golden/citetally_v1.summary.json` repeats that header on its own, so reports never need to open the main file. `tools/synthetic/golden.py` validates the file (`problems()`): at least 150 documents, unique ids, each family in one split only, at least a third of families held out, expected checks equal to those implied by the planted problem, duplicates pointing at a document in the same split, all 12 kinds present.

### D-022. How problems are planted
About a quarter of documents (55 of 210) carry exactly one of the 12 kinds, four or five of each. `tools/synthetic/planting.py` changes the numbers and prints again, so truth is what is on the page. Each kind breaks exactly one check; tests prove the arithmetic checks match (for example a planted line error leaves subtotal, tax and total consistent with it). Duplicates repeat a clean earlier document of the same vendor and layout (so they always fall in the same split). Outliers need a vendor with at least six documents and scale quantities past 3.4 times the vendor's median. Unknown-vendor documents come from three invented vendors that are not in the vendor list. So that planted problems are the only ones, natural documents are redrawn if their total is far from the vendor's median, and dates are moved if two natural documents from one vendor have the same total within ten days.

### D-023. The demo set is committed, the rest of the generated data is not
`python -m tools.synthetic.build` makes all 210 documents in about 2.5 minutes (62 MB) under `data/synthetic/docs/` and `data/synthetic/heldout/`, which are git-ignored and rebuilt from the seed. Committed: `eval/golden/citetally_v1.json`, its summary file, `universe/facts.json`, and the 12-document demo set in `data/synthetic/demo/` with its manifest (`.gitignore` has one exception for that folder). The demo set comes from the tuned split only and shows clean documents in several conditions and the main planted problems. Plan task 7 says "demo loader that loads a small labelled demo set for the UI"; Phase 1 prepares the folder and manifest (`python -m tools.synthetic.demo`), and putting the files into the app waits for the upload route (Phase 5) and the Inbox demo button (Phase 7).

### D-024. Phase 1 acceptance results
Checked 2026-10-30. Generation is deterministic: two full builds from seed 20261031 produced the same digest over all 210 files. A script (`python -m tools.synthetic.report`) prints counts by split, condition, family and planted kind: 140 tuned and 70 held-out documents, 55 with one planted problem (42 tuned, 13 held out), all four conditions in both splits, 15 families. Documents of every layout and condition were looked at by eye (contact sheets of all 15 families, and the four conditions in tuned and held-out damage). Findings fixed: the tax rate was in the answer key but not drawn on the per-line-tax layout; phone photos had black wedges around the page; the held-out fax-style scan turned shadowed areas into noise; a long date touched its label on the left-header layout. The golden file validates against its schema (`problems()` returns nothing), and held-out families appear in no tuned document. Known limit: these documents are cleaner and more regular than real ones, there is no handwriting, and the same author wrote the generator and the layouts, so results on them show the pipeline works, not how it behaves on a real business's files.

## Phase 2

### D-025. Migrations and the database module
`db/migrations/0001_init.sql` is the SQL block of `docs/BACKEND_SCHEMA.md` section 2, extracted unchanged (17 tables, 9 indexes). `citetally/db.py` applies pending migrations in order, each in its own transaction, and records them in `schema_migrations`. A migration that fails rolls back completely, leaves earlier ones applied, and can be run again once fixed. It refuses a folder with a bad file name, a duplicated number, a gap, or an applied migration whose file has gone missing. Connections run in autocommit mode (so transactions are explicit: `transaction(conn)`), with foreign keys on, a 5-second busy timeout, and WAL for file databases. Timestamps come from one helper (`now()`), ISO 8601 UTC to the millisecond. `python -m citetally.db migrate` migrates and seeds the database at `CITETALLY_DB_PATH` (default `data/citetally.db`, git-ignored). Seeding inserts only categories that are missing and never renames one the user has edited.

The schema document says an applied migration must never be edited but gives no way to detect an edit. None is added: `schema_migrations` has no checksum column and changing it is outside the schema. Review keeps this rule for now.

### D-026. The food category is labelled "Food and drinks"
`BACKEND_SCHEMA.md` labelled `FOOD` "Food and treats", which belongs to a pet business. The demo business is a plumbing company (D-015), so the label in `db/seed/categories.json` and in the schema document is "Food and drinks". The code `FOOD` is unchanged. The sample JSON in the schema document still mentions a pet vendor; those are illustrations only.

### D-027. Phase 2 branch workflow
From Phase 2 each phase is built on its own branch (`phase-2-data-layer`), pushed to GitHub, and merged to `main` through a pull request when its acceptance check passes. Phases 0 and 1 were built directly on `main` before this was decided.

### D-028. Models, enums and what the sync tests compare
`citetally/models.py` defines every enumeration once, as `StrEnum`s in the document's order, plus `EditField` (the header and line fields with `category` and `entry_type`, matching the `field_edits` constraint), `EventType` (audit event names, which the schema leaves unconstrained), the blocking-check set and `required_fields()`. One row model per table (all 17), with the table's exact columns; a test checks fields against `PRAGMA table_info` and nullable columns against optional fields, so a column added to a migration without a model fails the suite. `0/1` columns are `bool` in the models. `Word`, `ExtractedLine` and `ExtractedFields` validate the JSON shapes: extracted values must be text or null (a number such as `23.11` is rejected, because the model copies printed text and never reformats) and unknown keys are rejected.

`tests/test_models.py` compares three things: the enumeration table and the severity table parsed out of `docs/BACKEND_SCHEMA.md`, the enums in code, and every `CHECK (column IN (...))` in the migrated database (all 15 are mapped, and an unmapped new one fails). It was checked by hand: a one-letter typo in an enum value fails two tests. The provider list in `config.py` is checked against the `Provider` enum too.

### D-029. Audit events: a closed list of payload keys, no free text
`citetally/events.py` writes one `audit_events` row and one JSON log line per event. A payload may only use a short list of keys, each with a closed vocabulary (read method, OCR engine, check code, export profile, provider, extract mode, decision, stage, trigger), a number (counts, timings, confidence, ids) or a flag. There is no key for free text on purpose: an invoice number or a vendor name looks like any other identifier, so a pattern check on a text field cannot tell them apart. Model name and prompt version are therefore not event keys; they are columns of `extractions`. Error messages name the refused key and never echo the value. Unknown keys, wrong value types and values outside a vocabulary raise `PayloadError`, and nothing is stored.

`tests/test_events.py` covers the rule the schema asks for ("a test enforces this"): it tries every kind of content (vendor name, invoice number, amounts, page text, an injected instruction) as keys and values, then checks the captured log output and the stored rows contain none of it. Removing the key allowlist by hand makes 10 of its tests fail. `configure_logging()` sends lines to stderr as bare JSON and returns its handler, and the API will call it at start-up in Phase 5.

### D-030. Order of Phase 2 tasks 3 and 4
The state machine (task 3) was built before the audit helper (task 4), but the repository's status-change function (the rest of task 3) must record an audit event in the same transaction as the status change, so the audit helper was built first and the repository last.

### D-031. Repositories and the rules they enforce
`citetally/repository.py` (not listed in `docs/TRD.md` section 3; added for the "repository functions" task) is the only place that writes to the database. Rules enforced there, each with a test:

- **Status changes** (`change_status`) follow the state machine, run in one transaction, and write an audit event. A failure needs a stage from the allowed list and a plain written reason. A duplicate needs an existing, different document. A document needs an entry before it becomes extracted, needs review or approved. Approval needs every one of the eight blocking checks recorded and either passed or overridden with a written reason (a check that has not run counts as unresolved). A refused change leaves no row and no event.
- **Reprocessing** (needs review, rejected or failed back to received or read) clears what the re-run stages produce: checks and the entry with its lines, evidence and edit history, and the pages too when starting from received. Extraction attempts stay as history, and the next attempt gets the next number. `field_edits` is deleted with its entry because the schema says so.
- **Overrides** apply only to failed blocking checks, need a written reason, and are cleared whenever the check runs again, so an override always matches the values the reviewer saw.
- **Reviews** (`record_review`) change the status, store the review row (counting overrides, and whether anything was edited since the previous review of that document) and log a `review_recorded` event, all together. Rejecting needs a reason; marking a duplicate needs the original's id.
- **Values.** Amounts must be whole integers (a float, a bool or a string is refused), quantities, unit prices and tax rates must be exact decimal strings (`"2.5"`, never `"7%"`, `NaN` or a float), dates must be real `YYYY-MM-DD` dates, currencies three capital letters, and page boxes fractions of the page in order.
- **Queries** from `BACKEND_SCHEMA.md` section 5 (review queue, duplicate lookups by number and by content, vendor history) are implemented as written.

`db.now()` is now strictly increasing inside a process, so rows written one after another always sort in write order. Not built yet because their phases need them: exports and export items (Phase 6), vendor-name normalisation and matching (Phase 4; `create_vendor` takes the normalised name as an argument), and the `approved` to `exported` change, which `change_status` already allows.

### D-032. A small mismatch in the schema document
`BACKEND_SCHEMA.md` says every table has `created_at`, but `schema_migrations` has `applied_at`, `settings` has `updated_at`, and `export_items` has no timestamp. The tables are built as written; only the sentence is inexact.

## Phase 3

### D-033. How printed amounts and dates are read
`citetally/money.py` and `citetally/dates.py` read exactly what is printed and guess nothing; text that is not exactly one clean amount or date returns `None`. A lookalike letter ("1O0.00") is never corrected. The module `money.py` contains no float at all, and a test checks the source for the word.

**Amounts.** Currency symbols and codes before or after the number, `(45.00)`, a leading, trailing or true minus sign, and thousands grouped by commas, dots, spaces, no-break spaces or apostrophes are all read. When both `.` and `,` appear, the last one is the decimal mark whatever the locale, so a euro invoice reads correctly even under `en-US`. A mark that repeats ("1.234.567") only groups thousands. A mark that appears once before a number of digits other than three is a decimal mark ("12,50"). **A mark once before exactly three digits ("1.234", "1,234") reads two ways**: `parse_money` flags it ambiguous (the example in `docs/TRD.md` section 4.4) and the locale picks the value. A bare `$` means the business's dollar (`dollar="USD"` by default), not necessarily US dollars; `US$` and `CA$` are explicit. Indian-style grouping ("1,23,456") and mixed layouts are refused.

**Quantities and unit prices** (`parse_decimal`) follow the locale for that same lone mark without a flag, because three decimals are normal there: fuel is sold by the thousandth of a gallon (`11.699`) and a gallon costs `4.159`. Flagging every fuel receipt would be noise.

**Rates** (`parse_rate`) need a `%` sign; a bare `0.07` is not guessed to mean seven percent.

**Dates.** Year-first forms are always year, month, day. `/` and `-` numeric dates can be month-first or day-first: if both readings are real dates and differ, the date is flagged ambiguous and the locale picks (`en-US` month first; `en-GB`, `de-DE`, `fr-FR` and others day first). Dots mean day.month.year and are not flagged. Two-digit years pivot at 70 (69 is 2069, 70 is 1970). Only English month names, ordinals ("14th") and years 1900 to 2099 are understood; compact `20260314` and dates with extra words are not parsed.

**Locales** are a small fixed table in each module; an unknown locale is an error rather than a default.

Tests include round trips against the independent test-data printers (every money style and every date style, thousands of random values), and a cross-check that the product's line and tax arithmetic agrees with the separate arithmetic that made the golden set.

### D-034. Ingest: what it accepts, stores and refuses
`citetally/ingest.py` judges a file by its leading bytes only. The PDF marker must be the first bytes of the file (real readers tolerate junk before it; this does not, because a file whose first bytes are not a PDF header is more likely disguised than old). The upload limits (`CITETALLY_MAX_FILE_MB`, `MAX_PAGES`, `MAX_IMAGE_PIXELS`, `TEXT_LAYER_MIN_CHARS`) are settings, and an image's size is read from its header before any pixel is decoded, so a small file that claims to be huge is refused quickly (tested with a 256-megapixel PNG of under a megabyte). PDF pages are measured before they are rendered, so a tiny PDF with an enormous page box cannot allocate gigabytes. Pages are rendered at 200 dpi to PNG in `data/pages/<document id>/<n>.png`; images get their EXIF orientation applied and are flattened to plain RGB.

**Parsing runs in a separate process.** `isolated_call` starts a fresh process, kills it at the timeout (60 seconds) and reports a crash or exception by kind only, never with a message that could hold file content. A hung or crashing PDF library therefore fails one document, not the server. Starting a process costs about a second, so tests mostly run the same code in-process (`isolate=False`) and a few run the real worker.

**Storage.** The original is written to `data/files/<sha256>` through a temporary file and renamed, never overwritten, never named from the upload. The uploaded name is kept only as display text with folders, control characters and direction overrides removed. A file larger than the size limit is not stored at all.

**Duplicates.** A file whose hash matches an earlier document that has not failed becomes a new `duplicate` document pointing at the earliest one; nothing is stored or rendered again. A matching document that failed is not counted, so re-uploading after raising a limit works. `source_kind` is `digital_pdf` when at least half the pages have the minimum amount of printable text, otherwise `scanned_pdf`.

**A gap between two documents.** `docs/TRD.md` section 14 says a wrong-type file is `failed` at `ingest`, and the state machine allows `received` to `failed` for it, but `documents.mime_type` has a `CHECK` that allows only the three supported types, so no row can describe a file of another type. Followed the schema: an unsupported file raises `IngestRejected` with a plain reason and creates no row (the API will answer with an error, Phase 5). Files that are a supported type but too large, too long, too big in pixels or damaged do get a `failed` row with a plain reason.

`pillow`, `numpy` and `pypdfium2` moved from the development requirements to the runtime requirements, because the product now uses them.

### D-035. Reading the PDF text layer, and building the text the model sees
`citetally/reading/text_layer.py` takes words from the file's own text with pypdfium2. Words are split at the spaces the file or pdfium writes. A word is also split at a new line, or at a gap wider than 0.6 of the line height where the file wrote no space. Both tests use the font's line box (`get_charbox(loose=True)`), which has one height for every glyph. The ink box does not: it is short for "-" and "r" and tall for "M", and judging on it cut words into "M ill" and "SYNTH ETIC" and dropped "CN-20110". The ink box is still what is stored as the word's position, so a highlight sits on the printed value. A page whose text is too short or garbled (`looks_sane`) returns `None`, meaning "use OCR for this page".

`citetally/reading/layout.py` builds the aligned text from words with boxes. Words join a line when their centres are within 0.6 word heights, lines read top to bottom, and the gaps become spaces in proportion to the page width (at most 160 columns). A gap of 1.8 line pitches leaves one blank line. Columns count from the leftmost word on the page, so the page margin is not turned into leading spaces and a lone word comes out as itself. Control, format, surrogate, private-use and unassigned characters, and the replacement character, are removed from each word, and whitespace inside a word is collapsed. Nothing else is added, dropped or reordered, and a test checks that every printed value of every template family survives from PDF to words to text.

### D-036. Pre-processing without OpenCV
`citetally/reading/preprocess.py` is built on Pillow and NumPy only. D-016 said to recheck OpenCV's license before Phase 3 used it: the pip wheels bundle FFmpeg libraries, which are, as far as I know, LGPL, and `CLAUDE.md` rule 10 treats that as copyleft. Nothing in this step needed OpenCV, so it is not added and nothing is installed. If a later step needs it (for example to straighten perspective), decide then.

**Steps.** Scale so the long side is 1800 to 2400 pixels, flatten uneven light (divide by a smoothed paper estimate that skips over ink), median filter 3 for speckle, turn a sideways page a quarter turn, remove tilt, turn an upside-down page over, stretch contrast (darkest 1% to black, median to white). Estimates for the turns ignore anything the page mask calls desk (below half the brightness of the brightest tenth) and anything lighter than 190 on the flattened image, so a desk, a shadow edge or the page's own edge is not mistaken for text.

**How each turn is decided.** *Tilt*: the angle (within 12 degrees) that makes the row profile of ink most peaked, searched coarse to fine down to 0.05 degrees. `skew_degrees` is positive when lines rose to the right. *Sideways*: columns are more peaked than rows by a factor of 1.3, each axis at its own best tilt. *Upside down*: inside a line of text the ink falls away faster at the bottom (baseline, few descenders) than it rises at the top (capitals, ascenders); the evidence is the share by which it does so, and a page is turned over only when the evidence is below -0.02. A page of capitals or digits is symmetrical and is left as it is.

**Boxes map back.** OCR boxes come from the cleaned image, but the interface draws them on the stored page image. Every rotation is recorded as a `Turn`, and `Preprocessed.word_on_original` undoes them in reverse order, so evidence boxes land on the page the person sees. The cleaned image itself is not stored.

**What was measured** (by hand, on the development documents, one in six; not a committed test): on every page as stored, the upright-versus-upside-down evidence had the right sign, 35 of 35, in all four conditions (typically 0.05 to 0.15 for upright pages; the weakest was 0.03). With a known extra rotation added (0, 90, 180, 270 degrees, with and without 4 degrees of tilt), the right orientation was found on 48 of 48 clean PDFs, 40 of 40 light scans, 52 of 56 phone photos and 40 of 48 heavy scans. All eight misses on heavy scans and all four on phone photos came with the extra tilt; nothing is known about why for phone photos. A strong straight edge of the page against a lighter scanner background can dominate the tilt estimate (the measured tilt equalled the rotation I had added), and it is the likely cause for heavy scans. Tilt is accurate to about 0.1 degree on clean pages. Cost is 1 to 2 seconds a page.

**Known gaps.** Perspective is not corrected (phone photos have lines that slope differently at the top and the bottom of the page, so one tilt is a compromise). The constants above are starting values chosen on the development documents only. Whether pre-processing helps OCR at all is for the OCR bake-off to show (Phase 3, task 8); until Tesseract is installed, nothing here has been measured against reading accuracy.

### D-037. The OCR interface and the Tesseract wrapper
`citetally/reading/ocr.py` defines `OcrEngine` (`name`, `read_page(image) -> OcrPage`), `TesseractOcr` and `FakeOcr`. `read_page` takes a Pillow image, the cleaned page from `preprocess`, rather than the `PageImage` row of `docs/TRD.md` section 5, which only names a stored file; the pipeline will pass the cleaned image and map boxes back with `Preprocessed.word_on_original`. `OcrPage` holds the words (boxes as fractions of the image, confidence 0 to 100) and the mean confidence, which is `None` when no words were found.

**Tesseract** runs as a separate process with a timeout (120 seconds), on a temporary PNG that is removed afterwards, and its `tsv` output is parsed. Only word rows with text, a confidence of 0 or more and a box with area are kept. Starting values: English, `--psm 4`, `--dpi 200` (the page mode is superseded by D-040: mode 11). On one heavy scan, `--psm` 3, 4, 6 and 11 found 76, 73, 94 and 86 words at mean confidence 66, 70, 49 and 70, in about half a second each; that is one document and no accuracy measure, so the choice is for the bake-off (task 8). Errors say which kind of failure happened (`OcrUnavailable` for a missing or unstartable program, `OcrError` for a non-zero exit or a timeout) and carry nothing from the page or from Tesseract's own messages. The program is found from `TESSERACT_CMD`, then PATH, then the default Windows folders, the same order `tools/check_env.py` uses.

**Tests** need no OCR program: a recorded Tesseract output (`tests/fixtures/tesseract_clean_1700x2200.tsv`, from a synthetic invoice) is replayed through the parser, and the command line is checked with an injected runner. One test runs the real program and is skipped when it is not installed; it checks only that the wrapper works, not how well it reads. `FakeOcr.name` is `fake`; `events.py` allows only `tesseract` as an `ocr_engine` value, so the pipeline must not put a fake engine's name in an audit event until that is decided.

### D-038. What gets masked, and what does not
`citetally/reading/masking.py` hides card numbers and labelled bank account numbers. It is plain code with tests, and runs before any model call.

**Card numbers** are runs of 13 to 19 digits that pass the Luhn check *and* have a card network's starting digits and length (Visa, Mastercard including the 2-series, American Express, Discover, Diners, JCB, UnionPay). The network test is there because a Luhn check alone passes one random number in ten. Even so, about 3% of random 16-digit references pass both (measured on 200,000; the test's ceiling is 5%), so a 16-digit invoice number can be masked by mistake; none of the synthetic templates prints one, and a test checks that no printed value of any template family changes. A run is digit groups joined by single spaces or hyphens. It is not masked when it is glued to letters or a reference (`INV-4111...`), is an amount (`4111111111111111.50`, thousands separators), or is a negative number. Only the last four digits stay visible.

**On the stored words** (`mask_words`): digits OCR split into several words on one line are joined for the check, as long as the words are close together (3 letter-widths), so a card cannot get past by being read in pieces. The words keep their order, boxes and confidences; only the text changes. A card split over two lines, or over columns far apart, is not recognised. A span may begin with a stray digit group just before the card; that group is masked too, never the other way round.

**Labelled numbers** (`mask_labelled_numbers`, text only, not the stored words): account, routing and ABA numbers (six or more digits) and IBANs, when the label on the same line says so ("Account number", "Acct no", "Bank account #", "Routing number", "ABA", "IBAN"), with the last four characters left visible. Labels that only look similar are left alone on purpose: the utility template's invoice number is printed as "Account bill no.", and masking it would hide a value the model must copy. A real customer-account label such as "Account No." on some other template would be masked, and if that were the field the model must copy, grounding would then fail it; if such a template appears, handle it then.

**Not covered.** The page image still shows everything (TRD section 11), so the image mode stays off by default. Account numbers in a column apart from their label are not found. Because the stored words are masked, the evidence view shows the masked text over a page image that still shows the digits.

### D-039. Security tests for the read path, and the three defects they found
`tests/test_security.py` covers what `tests/test_ingest.py` does not (that file already covers type by content, size, page and pixel limits, damaged and password-protected files, filenames, and the isolated worker). New cases: a hand-built PDF with a JavaScript open action, a launch action that would write a file, a link annotation and an embedded program (ingest accepts it, starts no process, opens no connection, writes no marker file, and keeps the upload byte for byte); page text that looks like markup or instructions comes back as plain words; a 43 KB PDF that inflates to 30 MB finishes in about a second; seeded mutations of PDFs (in the isolated worker), PNGs and JPEGs end in a plain refusal or a read, never an exception or a hang; SVG, HTML, ZIP, TIFF, WebP, script and program files are refused whatever their name says; a file exactly at the size limit is accepted and one byte over is not; 500 random hostile names always give a clean display name, and cleaning twice changes nothing; a failing or slow OCR program never puts its output in an error; and masking and layout finish quickly on text built to cause backtracking or enormous words.

**Defects found and fixed.**
1. `preprocess` hung on a very thin image: a 3 by 5000 image made the tilt-search copy 700 pixels wide and over a million rows tall. The copy is now bounded in both directions (`_search_copy`).
2. `parse_tsv` accepted a confidence of `nan`, giving a word and a mean confidence of `nan`. It is now dropped; `inf` and anything above 100 become 100.
3. Nothing limited the length of a single word, so a text layer holding one million-character "word" went straight into the model's text. `clean_token` now cuts a word at `MAX_WORD_CHARS` (200); no printed value is that long. Separately, `is_card_number` now checks length and network before the Luhn sum, which halves the cost of masking a very long run of digit groups (about 11 microseconds per group, linear).

**For later phases.** `text_layer.read_pdf` and `extract_words` loop in Python over every character and are not time-limited, so the pipeline must call them through `ingest.isolated_call`, as ingest does for rendering; the same goes for `preprocess` and OCR. A text layer of millions of characters would otherwise tie up the worker. Uploads arrive as whole `bytes` here; the API (Phase 5) must refuse an oversize body while reading it, before this code sees it. Adversarial text aimed at the model (`SUSPICIOUS_TEXT`) is Phase 5.

### D-040. OCR bake-off, part 1: Tesseract settings and pre-processing (development split only)
`python -m tools.ocr_bakeoff` reads the 140 development ("tuned") documents; the held-out split is not opened (`load_golden` refuses it, and a test checks that). Truth for each page is the golden file's printed values (header fields and line items, as printed), so a score says whether the value a reviewer must check survives reading. *Found* means the printed string is in the page text exactly, or, for amounts, quantities and dates, some OCR word has the same digits. This is not the same as final extraction accuracy: it ignores wrong words that are not a printed value and how the model reads the text. The report is `eval/reports/ocr_bakeoff.json`. Speed is the median time to read one page with one thread, not counting pre-processing (about 2 seconds a page, shared by every cleaned configuration).

| Configuration | All values | clean_pdf | scan_light | scan_heavy | phone_photo | Numbers | s/page |
|---|---|---|---|---|---|---|---|
| **clean, mode 11 (chosen)** | **86.4%** | 98.2% | 96.3% | 64.0% | 86.5% | 89.8% | 0.56 |
| clean, mode 6 | 80.0% | 97.7% | 97.5% | 43.5% | 80.2% | 82.2% | 0.50 |
| clean, mode 3 | 72.2% | 98.3% | 96.7% | 43.2% | 49.8% | 72.3% | 0.52 |
| clean, mode 4 | 71.9% | 98.2% | 97.5% | 41.0% | 49.9% | 72.2% | 0.52 |
| cleaned but desk not whitened, mode 11 | 85.3% | 98.2% | 96.4% | 64.0% | 82.0% | 88.3% | 0.59 |
| raw (grey image only), mode 11 | 75.4% | 97.4% | 96.3% | 34.0% | 72.7% | 79.7% | 0.54 |
| raw, mode 4 | 64.9% | 99.4% | 96.7% | 9.9% | 51.7% | 66.3% | 0.54 |

**Choices.** Tesseract's sparse-text mode (`--psm 11`) beats the column modes by a wide margin, mostly on phone photos and heavy scans, where layout analysis fails on sloping or noisy tables; all modes are within two points on clean pages and light scans. Pre-processing helps: it takes heavy scans from 10% to 41% (mode 4) and from 34% to 64% (mode 11), and phone photos from 73% to 87% (mode 11). Two changes to `preprocess` came out of it: the desk around a photographed page is now whitened (+4.5 points on photos), and the median filter stays at 3 (no filter or size 5 were worse: 72.3% and 49.4% against 76.2% on heavy scans and photos together). Turning the page to pure black and white at 140 or 170 was worse still (58.0% and 48.3%). `TesseractOcr` now defaults to mode 11 with a 60-second timeout; D-037's mode 4 is superseded.

**A failure found on the way.** Mode 11 ran for more than two minutes on one heavy scan (`crn-0004`) where mode 6 took six seconds. A timeout now retries once in mode 6 before the page is reported as failed (`OcrTimeout`, a kind of `OcrError`). With that, all 140 pages were read in every configuration.

**What it shows.** Clean PDFs forced through OCR read at 98% (so the text layer remains the better source), light scans at 96%, phone photos at 87%, and heavy scans at 64%: money 64%, dates 67%, identifiers 68%, descriptions and names 43%. By type of value over all conditions: quantities 97%, dates 90%, amounts 88%, text 78%, identifiers (invoice and order numbers) 75%. By template, the weakest are T03 (69%) and T04 (79%). Mean OCR confidence is 92 on clean pages, 90 on light scans, 79 on photos and 60 on heavy scans, so the confidence signal separates the conditions that fail. Heavy scans will need the reviewer; `LOW_READ_QUALITY` has to fire on them.

**Still open for task 8.** The alternative engine. Nothing is added to the dependencies until it is chosen and its license checked (rule 10).

### D-041. OCR bake-off, part 2: the alternative engine, and the choice
The alternative is the OCR that ships with Windows 11 (`Windows.Media.Ocr`), reached through the MIT-licensed `winrt-*` Python packages. It was picked over RapidOCR because RapidOCR pulls in an `opencv-python` wheel with bundled LGPL FFmpeg, which rule 10 treats as copyleft, even for a tool that is never shipped. The seven `winrt-*` packages are pinned in `requirements-dev.txt` for Windows only (`sys_platform == "win32"`), so CI on Linux does not try to install them; the adapter is `tools/windows_ocr.py` and is used only by `tools.ocr_bakeoff`. It gives word boxes but no confidence, so a page read with it could not feed `LOW_READ_QUALITY`.

Same 140 development documents, same scoring as D-040 (values found / numbers found):

| Engine and input | All values | Numbers | clean_pdf | scan_light | scan_heavy | phone_photo | s/page |
|---|---|---|---|---|---|---|---|
| **Tesseract, cleaned, mode 11** | **86.4%** | **89.8%** | 98.2% | 96.3% | **64.0%** | **86.5%** | 0.58 |
| Windows OCR, raw page | 77.3% | 80.8% | 97.6% | 95.8% | 41.3% | 73.3% | 0.27 |
| Windows OCR, cleaned page | 61.2% | 64.4% | 81.8% | 85.7% | 32.9% | 43.3% | 0.21 |

**Choice: Tesseract, cleaned pages, sparse-text mode (11), 60-second timeout with a retry in mode 6.** It is nine points ahead of Windows OCR overall and far ahead where reading is hard (heavy scans 64% against 41%, phone photos 87% against 73%); the two are level on clean pages and light scans, where Windows OCR is twice as fast. Windows OCR was worse on the cleaned page than on the raw one (the clean-up was built and tuned for Tesseract), and gives no confidence. It is Windows-only and needs an OCR language pack, which the product could not assume. `OcrEngine` stays: a stronger engine can be added behind it later. `CITETALLY_OCR_ENGINE` stays `tesseract` only.

**What this does not settle.** Only two engines were compared; RapidOCR, EasyOCR or a vision model might read heavy scans better, and the question stays open for the vision experiment in Phase 4. The numbers are on the development split that the settings were chosen on, so they are optimistic; the held-out templates (T11 to T15) have not been read. Heavy scans at 64% mean most of them will reach the reviewer with values the page cannot confirm. That is the intended behaviour (`VALUE_IN_DOCUMENT`, `LOW_READ_QUALITY`) and Phase 8 reports it by condition.

**Phase 3 acceptance.** All 140 development documents read without crashing in every configuration; the report with accuracy by condition is `eval/reports/ocr_bakeoff.json` and the table above; the security tests pass.
