# Decisions

Decisions the planning documents do not cover. Newest last. Each entry: what, why.

## D-001: Planning documents live in `docs/`

`CLAUDE.md` and `TRD.md` section 3 both say the planning documents are in `docs/`, but they were delivered in the repository root. Moved them into `docs/` before the first commit. `CLAUDE.md` stays at the root.

## D-002: Directories and sub-packages created, empty module files not

`TRD.md` section 3 lists every module. Phase 0 creates the directories (`db/migrations`, `db/seed`, `eval`, `tools`, `tests`, `web`) and the sub-packages (`citetally/reading`, `citetally/checks`, `citetally/providers`). Individual module files (`db.py`, `money.py`, ...) are created in the phase that implements them, so there are no empty stubs to mislead a reader.

## D-003: Line endings fixed to LF

`.gitattributes` sets `* text=auto eol=lf` so Windows checkouts and the Linux CI runner agree and ruff's formatter does not report line-ending differences.
