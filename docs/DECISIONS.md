# Decisions

Decisions the planning documents do not cover. Newest last. Each entry: what, why.

## D-001: Planning documents live in `docs/`

`CLAUDE.md` and `TRD.md` section 3 both say the planning documents are in `docs/`, but they were delivered in the repository root. Moved them into `docs/` before the first commit. `CLAUDE.md` stays at the root.

## D-002: Directories and sub-packages created, empty module files not

`TRD.md` section 3 lists every module. Phase 0 creates the directories (`db/migrations`, `db/seed`, `eval`, `tools`, `tests`, `web`) and the sub-packages (`citetally/reading`, `citetally/checks`, `citetally/providers`). Individual module files (`db.py`, `money.py`, ...) are created in the phase that implements them, so there are no empty stubs to mislead a reader.

## D-003: Line endings fixed to LF

`.gitattributes` sets `* text=auto eol=lf` so Windows checkouts and the Linux CI runner agree and ruff's formatter does not report line-ending differences.

## D-004: Python dependencies pinned in two requirements files

`requirements.txt` holds runtime dependencies and `requirements-dev.txt` adds test and lint tools (`-r requirements.txt` plus pytest, ruff, mypy, httpx2). Both list every package, including transitive ones, at exact versions (a `pip freeze` of the virtual environment), so installs are reproducible. No extra lock tool. Phase 0 installs only what Phase 0 uses; later phases add `pdfplumber`, `pypdfium2`, Pillow, OpenCV, `reportlab` and so on, each after a license check.

Type checking is `mypy --strict` with the pydantic plugin (MIT). Lint and format are `ruff` (MIT). Ruff skips `docs/` and `web/`.

FastAPI's test client needs an HTTP client library. Starlette now deprecates `httpx` there in favor of `httpx2` (BSD-3-Clause), so the dev requirements use `httpx2`; this also avoids `certifi` (MPL-2.0).

## D-005: License check of Phase 0 Python dependencies

Checked every installed package. All are MIT, BSD, Apache-2.0 or PSF, with one exception: `pathspec` (MPL-2.0, weak file-level copyleft), pulled in by `mypy`. It is development-only, unmodified and not redistributed, so it does not affect the MIT license of this repository. No AGPL or GPL anywhere. `CLAUDE.md` rule 10 says "no AGPL or other copyleft", so this is flagged for the owner to accept or replace (replacing it means a different type checker).

## D-006: Settings use the names in TRD section 8, one class, `.env` optional

`citetally/config.py` has a single `Settings` class (pydantic-settings). Each field is bound to its documented variable name (`CITETALLY_*`, plus `OLLAMA_URL` and `TESSERACT_CMD`), empty values fall back to defaults so `.env.example` can ship with blank entries, and unknown variables are ignored. Phase 0 includes only the settings that exist so far. `CITETALLY_MODEL_PROVIDER=hosted` without `CITETALLY_ALLOW_HOSTED=true` fails at startup (TRD section 6). The API always binds to `127.0.0.1`; the host is not configurable.

The API app is built by `create_app(settings)` (run with `python -m citetally`), not a module-level global, so tests can build an app without reading the developer's `.env`.

## D-007: Shape of `/api/status` before most features exist

TRD section 7 lists the fields: provider, model, OCR engine, database health, hosted-mode flag, synthetic-data flag; section 10 adds last model call, OCR availability and queue depth. Phase 0 returns the configured values and returns `null` for database health, OCR availability, queue depth and last model call, because those parts are built in Phases 2 to 5. `null` means "not reported yet", not "unhealthy". Field names are `app`, `version`, `model_provider`, `text_model`, `vision_model`, `ocr_engine`, `hosted_mode`, `synthetic_data`, `database_ok`, `ocr_available`, `queue_depth`, `last_model_call_at`. `BACKEND_SCHEMA.md` does not name these, so confirm them when Phase 5 builds the real status endpoint.

## D-008: Web app setup

React 19, Vite 8, TypeScript, Vitest with Testing Library and jsdom, ESLint with typescript-eslint, all at exact versions in `web/package.json` with `package-lock.json` committed.

- **TypeScript 5.9.3, not 7.x.** The newest TypeScript (7.0) is outside the supported range of `typescript-eslint` (below 6.1) and `openapi-typescript` (5.x). 5.9.3 satisfies both.
- **Dev proxy, no CORS.** Vite serves on `127.0.0.1:5175` (strict port) and proxies `/api` to `127.0.0.1:8200`, so the browser sees one origin and the API needs no CORS configuration.
- **Generated types.** `python -m tools.export_openapi` writes `web/openapi.json` from the FastAPI app; `npm run gen:api` in `web/` turns it into `web/src/api/schema.d.ts`. Both files are committed. A pytest test fails if `openapi.json` is out of date, and CI fails if `schema.d.ts` is out of date with `openapi.json`.
- **Licenses.** All npm packages installed are MIT, ISC, BSD, Apache-2.0 or similar, with these exceptions, all build-time only and not shipped in the repository: `lightningcss` (MPL-2.0, weak file-level copyleft, a dependency of Vite) and `caniuse-lite` (CC-BY-4.0, browser-support data). No AGPL or GPL. Flagged with D-005 for the owner to accept.
- The status page renders every value as text. The hosted-mode banner is already wired to `hosted_mode`; its wording ("a hosted provider") becomes the provider's name when hosted mode exists.

## D-009: `tools/check_env.py` design

Standard library only, so it runs before the virtual environment exists. It reads `.env` (real environment variables win) and reports Python 3.13, Node.js, Tesseract (including the `eng` language data), Ollama reachability and which models are pulled, and whether the configured text model (and vision model, if set) are among them. Tesseract is looked up from `TESSERACT_CMD`, then `PATH`, then the default Windows install folders. It prints Windows install hints (`winget install ...`) but never installs anything. It exits 0 whatever it finds; `--strict` exits 1 if anything is missing. Machine access goes through an injected `Probes` object, so its tests need no Tesseract, no Ollama and no network. It only accepts `http://` or `https://` for `OLLAMA_URL`.

Node.js is included because the web app needs it; this goes slightly beyond the plan's "Tesseract and Ollama".

## D-010: CI

`.github/workflows/ci.yml` has two jobs on `ubuntu-latest`, Python 3.13 and Node 24, running on pushes to `main` and on pull requests with read-only permissions. The Python job runs `ruff check`, `ruff format --check`, `mypy` and `pytest`. The web job runs `npm ci`, ESLint, `tsc`, Vitest, and regenerates the API types to confirm `web/src/api/schema.d.ts` matches `web/openapi.json`. Nothing needs a model, an OCR binary or network access, and nothing deploys. Action versions are pinned to the latest major releases at the time of writing (checkout v7, setup-python v7, setup-node v7). The workflow has not run yet because there is no GitHub remote; the same commands were run locally, and the pinned requirements were installed into a fresh virtual environment to confirm they resolve.
