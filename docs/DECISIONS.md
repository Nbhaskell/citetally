# Decisions

Decisions the planning documents do not cover. Newest last. Each entry: what, why.

## D-001: Planning documents live in `docs/`

`CLAUDE.md` and `TRD.md` section 3 both say the planning documents are in `docs/`, but they were delivered in the repository root. Moved them into `docs/` before the first commit. `CLAUDE.md` stays at the root.

## D-002: Directories and sub-packages created, empty module files not

`TRD.md` section 3 lists every module. Phase 0 creates the directories (`db/migrations`, `db/seed`, `eval`, `tools`, `tests`, `web`) and the sub-packages (`citetally/reading`, `citetally/checks`, `citetally/providers`). Individual module files (`db.py`, `money.py`, ...) are created in the phase that implements them, so there are no empty stubs to mislead a reader.

## D-003: Line endings fixed to LF

`.gitattributes` sets `* text=auto eol=lf` so Windows checkouts and the Linux CI runner agree and ruff's formatter does not report line-ending differences.

## D-004: Python dependencies pinned in two requirements files

`requirements.txt` holds runtime dependencies and `requirements-dev.txt` adds test and lint tools (`-r requirements.txt` plus pytest, ruff, mypy, httpx). Both list every package, including transitive ones, at exact versions (a `pip freeze` of the virtual environment), so installs are reproducible. No extra lock tool. Phase 0 installs only what Phase 0 uses; later phases add `pdfplumber`, `pypdfium2`, Pillow, OpenCV, `reportlab` and so on, each after a license check.

Type checking is `mypy --strict` (MIT). Lint and format are `ruff` (MIT).

## D-005: License check of Phase 0 Python dependencies

Checked every installed package. All are MIT, BSD, Apache-2.0, PSF or similar permissive licenses, with two exceptions that are **weak copyleft (MPL-2.0, file-level)**: `certifi` (pulled in by `httpx`, used by FastAPI's test client) and `pathspec` (pulled in by `mypy`). Both are development-only, unmodified and not redistributed, and MPL-2.0 does not affect the MIT license of this repository. No AGPL or GPL. `CLAUDE.md` rule 10 says "no AGPL or other copyleft"; this is flagged for the owner to accept or replace. To drop `certifi`, tests would need a client other than `httpx`; to drop `pathspec`, a different type checker.
