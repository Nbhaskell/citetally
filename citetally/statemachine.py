"""The document status state machine. See docs/BACKEND_SCHEMA.md section 4.

Pure rules, no database: which status can follow which, and what a transition must carry
(a failure stage when failing, a pointer when marking a duplicate). The repository applies
these rules and keeps the database in step.
"""

from __future__ import annotations

import itertools

from citetally.models import DocumentStatus as S
from citetally.models import Stage

_SINGLE: dict[tuple[S, S], str] = {
    (S.RECEIVED, S.READ): "read_finished",
    (S.RECEIVED, S.DUPLICATE): "duplicate_file",
    (S.RECEIVED, S.FAILED): "failed",
    (S.READ, S.EXTRACTED): "extract_finished",
    (S.READ, S.FAILED): "failed",
    (S.EXTRACTED, S.NEEDS_REVIEW): "checks_finished",
    (S.EXTRACTED, S.FAILED): "failed",
    (S.NEEDS_REVIEW, S.APPROVED): "approved",
    (S.NEEDS_REVIEW, S.REJECTED): "rejected",
    (S.NEEDS_REVIEW, S.DUPLICATE): "marked_duplicate",
    (S.APPROVED, S.NEEDS_REVIEW): "reopened",
    (S.APPROVED, S.EXPORTED): "exported",
    (S.REJECTED, S.NEEDS_REVIEW): "reopened",
}
_REPROCESS_FROM = (S.NEEDS_REVIEW, S.REJECTED, S.FAILED)
_REPROCESS_TO = (S.RECEIVED, S.READ)  # received re-reads, read re-extracts

EDGES: frozenset[tuple[S, S]] = frozenset(
    {*_SINGLE, *itertools.product(_REPROCESS_FROM, _REPROCESS_TO)}
)

# Which stage a failure can be reported at, by the status the document was in.
FAILURE_STAGES: dict[S, frozenset[Stage]] = {
    S.RECEIVED: frozenset({Stage.INGEST, Stage.READ}),
    S.READ: frozenset({Stage.EXTRACT}),
    S.EXTRACTED: frozenset({Stage.GROUND, Stage.MATCH, Stage.CHECK}),
}


class IllegalTransition(Exception):
    """A status change the state machine does not allow."""


def is_reprocess(source: S, target: S) -> bool:
    return source in _REPROCESS_FROM and target in _REPROCESS_TO


def trigger_for(source: S, target: S, failure_stage: Stage | None = None) -> str:
    """A short fixed name for what caused the change. Safe to store and log: never document text."""
    if target is S.FAILED:
        return f"{failure_stage.value}_failed" if failure_stage else "failed"
    if is_reprocess(source, target):
        return f"reprocess_{target.value}"
    return _SINGLE[(source, target)]


def check_transition(
    source: S,
    target: S,
    *,
    failure_stage: Stage | None = None,
    duplicate_of: int | None = None,
) -> None:
    """Raise IllegalTransition unless `source` to `target` is allowed with this extra data."""
    if (source, target) not in EDGES:
        raise IllegalTransition(f"A document cannot go from {source.value} to {target.value}.")
    if target is S.FAILED:
        allowed = FAILURE_STAGES[source]
        if failure_stage not in allowed:
            names = ", ".join(sorted(s.value for s in allowed))
            raise IllegalTransition(
                f"Failing from {source.value} needs a failure stage, one of: {names}."
            )
    elif failure_stage is not None:
        raise IllegalTransition("A failure stage is only allowed when the status becomes failed.")
    if target is S.DUPLICATE:
        if duplicate_of is None:
            raise IllegalTransition("Marking a duplicate needs duplicate_of, the original's id.")
    elif duplicate_of is not None:
        raise IllegalTransition("duplicate_of is only allowed when the status becomes duplicate.")
