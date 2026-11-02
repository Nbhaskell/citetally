# Hardening review (Phase 9)

All documents are invented. This records what was checked, what was found, and what was changed. Each check can be run again from the commands given.

## Result in one table

| Task | Result | Open findings |
|---|---|---|
| 1. Security tests, fuzzing, timeouts, worker isolation | 500 damaged files run through ingest and reading: no crash, hang or stray file | none |
| 2. Dependency audit and licenses | No known vulnerabilities in Python packages or in what ships to the browser; no AGPL or GPL anywhere | 13 moderate advisories in developer tools only (see below) |
| 3. Log review | A new end-to-end test finds no document text in any log line, output or audit row; one leak found outside it (search text in the server's access log) and fixed | none |
| 4. Failure drills | 15 drills pass; two gaps found (disk full) and fixed | none |
| 5. Performance | Median 5.3 to 8.6 seconds per page by condition | none (limits noted) |

No high-severity finding is open.

## 1. Security tests, fuzzing, timeouts and isolation

The existing tests (`tests/test_security.py`, `tests/test_ingest.py`, `tests/test_nothing_is_sent.py`) were run again and pass: type by content, size, page and pixel limits, decompression bombs, active content in PDFs, filenames with path characters, a hung parser killed at its timeout, a crashing worker reported without its message.

New: `tools/fuzz_ingest.py` damages the invented demo files (flipped, deleted, inserted, repeated, zeroed and truncated bytes, splices of two files, header-only files, junk appended), then puts each through `ingest` and the whole pipeline with the real Tesseract and a fake model. Same seed, same files. Counts only are kept (`eval/reports/fuzz_ingest.json`).

| Seed 1, 500 cases | Result |
|---|---|
| Reached the review queue | 288 |
| Failed with a plain reason | 210 (201 "The file could not be read. It may be damaged or locked."; 8 "No text could be read…"; 1 "too much text") |
| Refused as not a PDF, PNG or JPEG | 2 |
| Exception escaped, ended in an unknown status, or slower than 120 seconds | 0 |
| Files written outside the data folder | 0 |
| Slowest case | 65.8 seconds (a PDF with a repeated chunk) |

Parsing and rendering run in a separate process with a timeout (`ingest.isolated_call`), and page reading in the pipeline does the same, so a damaged file takes down a worker process, not the server.

Not covered: files larger than the 20 MB limit are refused before parsing and were not fuzzed; fuzzing used the invented documents as seeds, so it reaches the parsers' damage handling and not every format feature.

Run again: `.\.venv\Scripts\python.exe -m tools.fuzz_ingest --cases 500 --seed 1` (about 25 minutes).

## 2. Dependencies and licenses

- **Python** (`pip-audit` on `requirements-dev.txt`, pinned versions): no known vulnerabilities. `pip-licenses`: MIT, BSD, Apache-2.0, PSF, MIT-CMU and similar. The one weak-copyleft package is `pathspec` (MPL-2.0, a development tool pulled in by `mypy`, not shipped), already accepted in D-005. `pypdfium2` carries BSD-3-Clause and Apache-2.0 for itself and the PDFium library it bundles.
- **Web** (`npm audit`): 0 vulnerabilities in what is shipped (three production packages, all MIT). 13 moderate advisories, all one: `minimatch` denial of service through pathological glob patterns, reached through `eslint`, `typescript-eslint` and `openapi-typescript`. These run only on a developer machine and in CI on the repository's own patterns; nothing in them is shipped or reads a document. The fix is a breaking upgrade of those tools, so it is left for a routine upgrade. Licenses of the 278 packages in the lock file: MIT, ISC, BSD, Apache-2.0, BlueOak, MIT-0, CC0, one Python-2.0 (a build-time argument parser), `caniuse-lite` data under CC-BY-4.0, and `lightningcss` under MPL-2.0 (a Vite build tool, accepted in D-008, not shipped). No AGPL or GPL.
- **Programs and models used but not bundled**: Tesseract (Apache-2.0), Ollama (MIT) and the `qwen3` model files. Check a model's own license before redistributing it.

Run again: in a separate throwaway environment, `pip install pip-audit pip-licenses`, then `pip-audit -r requirements-dev.txt --no-deps` and `pip-licenses --python <path to .venv python>`; and `npm --prefix web audit`. The audit tools are not added to the project's requirements.

## 3. Log review

The rule: logs and audit rows hold ids, stage names, timings and codes, never document text, vendor names, invoice numbers or amounts. `tests/test_events.py` covers the event writer. New: `tests/test_log_review.py` runs the whole app (API, worker, pipeline, review, export) with eleven recognisable strings planted in the page text, the model's reply, an exception message, a filename, a note, a line description, an override reason and a rejection reason, including three failing paths, then searches every log record at debug level on every logger, everything printed, and every audit row. None appears. The test also checks that the failure paths really ran.

**One leak found and fixed.** The inbox search sends what the person types in the address (`GET /api/documents?q=…`), and Uvicorn's access log prints the whole address to the console, so a vendor or invoice number typed there was logged. The server is now started with the access log off (`citetally/__main__.py`, D-060); a test checks the setting. Audit events carry the request id, so a request can still be traced.

What this does not show: the test client does not go through Uvicorn, so the setting is checked on its own, and anything a future code change logs outside these paths needs its own test.

## 4. Failure drills

`tests/test_failure_drills.py`. The model drills run the real Ollama client against a small local server that misbehaves; the OCR drill uses the real Tesseract wrapper pointed at a program that is missing.

| Drill | What happens | Matches the docs |
|---|---|---|
| Model closes the connection, sends half an answer, or sends a web page instead of JSON | Document `failed` at `extract` with a plain reason; the next document still runs; after the model is back, reprocessing gives one entry, not two | yes |
| Model never answers | Stopped at the timeout, `failed` at `extract`, "took too long" | yes |
| Model not running | `failed` at `extract`, "not running"; three queued documents all reach a result | yes |
| Tesseract missing | A scan `failed` at `read` naming Tesseract; a digital PDF still works from its text layer; `/api/status` reports OCR unavailable | yes |
| Disk full when saving the upload | Each file in the upload gets its own plain "refused, disk may be full" result; HTTP 200, no half-made document; the same file uploads fine once space is back | **No: it was an HTTP 500 for the whole request. Fixed.** |
| Disk full when writing the page pictures | Document `failed` at `ingest`, original kept, partial page folder removed | **No: an exception escaped and left a half-made document. Fixed.** |
| Page picture corrupt, empty or missing | That document `failed` at `read` with a plain reason; the next one is fine | yes |
| App stopped with documents waiting | All are picked up at the next start and reach the review queue | yes |
| App killed after the read stage | The document resumes at extraction with no double pages or entries | yes |
| Read and extract run again (reprocess) | Earlier results are replaced, not added to | yes |

The disk-full fixes are in `citetally/ingest.py` (D-060). Not drilled: filling a real disk, killing a real Ollama process (a stub stood in), SQLite reporting a full or locked database (it becomes the generic 500 with a request id, as the TRD describes), and power loss during a write.

## 5. Performance

`eval/reports/performance.md`, made from the saved evaluation runs (`python -m tools.evaluation.performance`; nothing is processed again). Whole path from upload to the review queue, one document at a time: median seconds per page 5.3 (clean PDF), 7.5 (light scan), 8.6 (heavy scan) and 8.0 (phone photo) on the development split, with the held-out split close (5.3, 7.5, 10.5, 7.2). The model call is the larger part of every median. The slowest documents are heavy scans, including the ones the model failed on twice. All golden documents are one page; multi-page documents and a busy machine were not timed.
