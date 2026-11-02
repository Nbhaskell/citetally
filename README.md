# Citetally

> **Work in progress.** This project is under construction and is not ready to use.

> **Demo data. All vendors, invoices and amounts are invented.** Every name, email address, phone number, invoice and receipt in this repository is synthetic. There is no real business data here.

Citetally is an AI review desk for invoices and receipts at a small business. PDFs and photos go in. It reads them, copies the printed values into structured line items, finds each value on the page, checks the arithmetic, duplicates and dates in code, and queues everything for a person to approve. Approved entries leave as a CSV for accounting software.

**Nothing is ever paid, posted or sent automatically.** The only output is a CSV the user downloads.

## Status

Phases 0 to 8 are built: repository and tooling, the invented business with 210 labelled documents in four conditions (the golden set), the data layer, document reading (text layer and OCR), model extraction with grounding, the checks, the review and approval screens, vendors, exports, insights and settings, and the evaluation. Phases 9 (hardening) and 10 (documentation) remain, so this is still a work in progress. See `docs/IMPLEMENTATION_PLAN.md` for the build order.

## How well it reads (measured on invented documents)

The numbers come from `eval/reports/`; the development split (140 documents) was used to look at errors, and the held-out split (70 documents, different layouts) was run once, after the development numbers were written down, on the system as shipped (OCR text and the local `qwen3:8b` model). Percent of printed header fields read exactly:

| Documents | Development | Held-out (one run) |
|---|---|---|
| Clean PDFs | 94.7% | 97.3% |
| Light scans | 92.1% | 80.0% |
| Heavy scans | 41.8% | 10.7% |
| Phone photos | 42.7% | 20.7% |
| All | 68.5% | 50.7% |

In short: clean PDFs work, and degraded scans and photos do not on the default path. On the development split, also giving the model the page image brought heavy scans to 94.1% and phone photos to 97.8%, but values read from the picture cannot yet be found in the OCR text, so every such document is flagged for review; that setting was not run on the held-out split. Across all conditions the checks blocked 67.3% (development) and 80.7% (held-out) of clean documents, so a person still reviews most of them. Everything is a person's decision to approve; nothing is paid, posted or sent.

These are invented documents with generated noise, 17 or 18 per condition on the held-out split, one machine and one model. Read the intervals and limits in `eval/reports/eval_dev.md`, `eval/reports/eval_heldout.md` and the two analysis files beside them before quoting a number.

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
