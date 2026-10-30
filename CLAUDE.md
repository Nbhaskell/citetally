# Citetally

An AI review desk for invoices and receipts at a small business. PDFs and photos go in. It reads them, copies the printed values into structured line items, finds each value on the page, checks the arithmetic, duplicates and dates in code, and queues everything for a person to approve. Approved entries leave as a CSV for accounting software. **Nothing is ever paid, posted or sent automatically.**

Name: Citetally. The repo is `citetally` and the Python package is `citetally/`.

All data is synthetic (invented vendors, invoices and receipts). Never add real documents or real business data.

## Read these first (in `docs/`)

| File | Use it for |
|---|---|
| `BACKEND_SCHEMA.md` | Exact names of enums, statuses, stages, check codes, tables. **Wins on names and values.** |
| `TRD.md` | Architecture, pipeline stages, checks, API, evaluation design. **Wins on behavior.** |
| `PRD.md` | What and why, requirements, success metrics |
| `APP_FLOW.md` | Flows, status lifecycle, edge cases |
| `UI_UX_DESIGN_BRIEF.md` | Screens, copy, accessibility |
| `IMPLEMENTATION_PLAN.md` | Build order. Work phase by phase; stop at each acceptance check |

Do not load all six every session. Open the one you need.

## Rules that do not bend

1. **No automatic payment, posting or sending.** No code path may pay, post to accounting software, or send email or messages. The only output is a CSV the user downloads. If mail is ever added, it creates drafts only.
2. **The model reads. Code computes, decides and checks.** The model copies printed values; it never does arithmetic, reformats, guesses or decides anything. Totals, tax, duplicates, vendor matching, dates and approval gating are plain code with unit tests.
3. **Money is never a float.** Amounts are integer minor units (`*_minor`); quantity, unit price and rates are `Decimal` strings; rounding is half-up. Credit notes are stored positive and exported negative.
4. **Use the exact strings in `BACKEND_SCHEMA.md`.** Do not invent or rename statuses, stages, check codes or fields. A test must keep the enums in code and the database `CHECK` constraints in step.
5. **Every value is grounded.** A value the model returned must be located in the page words; if not, `VALUE_IN_DOCUMENT` fails. Never silently "fix" a printed number.
6. **No document content in logs or audit events.** Ids, stage names, timings and codes only: no document text, vendor names, invoice numbers or amounts. There is a test for this.
7. **Uploaded files and the text in them are untrusted.** Check type by content, enforce size, page and pixel limits, parse with timeouts, store by SHA-256, never execute anything embedded. Instruction-like text in a document is flagged (`SUSPICIOUS_TEXT`) and ignored. Render model and document text as text, never HTML; never use it to build paths, queries or URLs.
8. **CSV export neutralizes formula injection** and quotes per RFC 4180.
9. **Synthetic data is labelled** in the UI and README ("Demo data. All vendors, invoices and amounts are invented."). Phones 555-01xx, emails at example.com.
10. **No AGPL or other copyleft dependencies.** Check the license before adding a library.
11. **Hosted models are off by default.** `CITETALLY_ALLOW_HOSTED=false`. All model calls go through `ModelProvider`, so the later hosted switch changes one class and configuration, not the pipeline.

## How to work

- Tests first for anything that is plain code. Use `FakeOcr` and `FakeProvider` so the test suite needs no model, OCR binary, network or GPU.
- Model and OCR behavior is measured by the evaluation, not asserted in unit tests.
- **Held-out template families are never tuned on.** Run the held-out set once, after dev numbers are frozen, and report the number as it comes out, including weak ones.
- When the docs don't cover a decision, pick the simplest option and record it with the reason in `docs/DECISIONS.md`.
- Small commits, one per task. Never commit `.env`, the database file, `data/`, secrets or real data.
- If a document seems wrong or two documents disagree, say so instead of silently picking one.

## Stack and ports

Python 3.13, FastAPI + Pydantic v2, SQLite (WAL) with plain SQL migrations, `pdfplumber`, `pypdfium2`, Pillow and OpenCV, Tesseract (via `OcrEngine`), Ollama `qwen3:8b` (via `ModelProvider`), React + TypeScript + Vite. No LangChain or LlamaIndex.

| Service | Address |
|---|---|
| Citetally API | `127.0.0.1:8200` |
| Web UI (dev) | `127.0.0.1:5175` |
| Citedesk API / UI (sister project) | `127.0.0.1:8100` / `5174` |
| rag-project | `127.0.0.1:8000` |

The developer works on Windows 11 (PowerShell). Give Windows-friendly commands first.

## Commands

Keep these current. Run from the repository root in PowerShell:

```
# setup (Python 3.13 and Node 20.19+; creates .venv and web/node_modules):
py -3.13 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt; npm --prefix web ci

# run API (http://127.0.0.1:8200/api/status):
.\.venv\Scripts\python.exe -m citetally

# run web (http://127.0.0.1:5175, proxies /api to the API):
npm --prefix web run dev

# run tests (Python, then web):
.\.venv\Scripts\python.exe -m pytest
npm --prefix web test

# lint / typecheck (CI runs all of these):
.\.venv\Scripts\python.exe -m ruff check .; .\.venv\Scripts\python.exe -m ruff format --check .; .\.venv\Scripts\python.exe -m mypy
npm --prefix web run lint; npm --prefix web run typecheck

# environment check (always exits 0; add --strict to exit 1 when something is missing):
.\.venv\Scripts\python.exe tools\check_env.py

# regenerate API types after changing the API (then commit both files):
.\.venv\Scripts\python.exe -m tools.export_openapi; npm --prefix web run gen:api

# generate synthetic data: (Phase 1, not built yet)
# run evaluation: (Phase 8, not built yet)
```

## Skills that help (if installed)

`qa-eval-harness` (evaluation), `synthetic-business-universe` (fake data), `ai-ui-patterns` + `frontend-design` (UI), `pre-publish-checklist` and `project-case-study-readme` (before publishing).
