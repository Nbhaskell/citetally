# Citetally

> **Work in progress.** This project is under construction and is not ready to use.

> **Demo data. All vendors, invoices and amounts are invented.** Every name, email address, phone number, invoice and receipt in this repository is synthetic. There is no real business data here.

Citetally is an AI review desk for invoices and receipts at a small business. PDFs and photos go in. It reads them, copies the printed values into structured line items, finds each value on the page, checks the arithmetic, duplicates and dates in code, and queues everything for a person to approve. Approved entries leave as a CSV for accounting software.

**Nothing is ever paid, posted or sent automatically.** The only output is a CSV the user downloads.

## Status

Phases 0 to 2 are built: repository and tooling, the invented business with 210 labelled invoices, receipts and credit notes in four conditions (the golden set), and the data layer (SQL migrations, enums and models kept in step with the schema document, the document state machine, repositories and audit events). The API answers `/api/status` and a React page shows it. Nothing reads a document yet. See `docs/IMPLEMENTATION_PLAN.md` for the build order.

## Run it (Windows, PowerShell)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm --prefix web ci
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m citetally
```

Then open <http://127.0.0.1:8200/api/status>. In a second terminal, `npm --prefix web run dev` serves the web page at <http://127.0.0.1:5175>.

Check the machine (reports Tesseract, Ollama and the pulled models; it never fails):

```powershell
.\.venv\Scripts\python.exe tools\check_env.py
```

Run the checks:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
npm --prefix web test
```

Turn on the commit guard that blocks personal information and committed secrets (once per clone; the second command downloads a checksum-verified copy of gitleaks into the git-ignored `.tools/` folder):

```powershell
git config core.hooksPath .githooks
.\.venv\Scripts\python.exe tools\secret_scan.py --fetch
```

## Documentation

Planning documents are in `docs/`. Start with `docs/PRD.md`, then `docs/TRD.md`. Decisions the plans do not cover are in `docs/DECISIONS.md`.

Part of a family of projects: [citedesk](https://github.com/Nbhaskell/citedesk), [citewise-markets](https://github.com/Nbhaskell/citewise-markets), [rag-project](https://github.com/Nbhaskell/rag-project), [citecheck](https://github.com/Nbhaskell/citecheck).

## License

MIT. See `LICENSE`.
