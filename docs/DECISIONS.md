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
