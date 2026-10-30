"""The document state machine: exactly the transitions in the schema document, nothing else."""

import itertools
import re
from collections import deque
from pathlib import Path

import pytest

from citetally import statemachine as sm
from citetally.models import DocumentStatus as S
from citetally.models import Stage

SCHEMA_DOC = Path(__file__).resolve().parent.parent / "docs" / "BACKEND_SCHEMA.md"


def documented_edges() -> set[tuple[S, S]]:
    """The transition table in docs/BACKEND_SCHEMA.md section 4, with grouped rows expanded."""
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    section = text.split("## 4. State machine", 1)[1].split("## 5. Queries", 1)[0]
    edges: set[tuple[S, S]] = set()
    for row in re.finditer(r"^\| ([^|]*`[^|]*) \| ([^|]*`[^|]*) \| [^|]+ \|$", section, re.M):
        sources = [S(v) for v in re.findall(r"`(\w+)`", row.group(1))]
        targets = [S(v) for v in re.findall(r"`(\w+)`", row.group(2))]
        edges.update(itertools.product(sources, targets))
    return edges


def test_the_allowed_transitions_are_exactly_the_documented_ones() -> None:
    documented = documented_edges()
    assert len(documented) == 19  # 13 single rows + the 6 reprocess pairs
    assert documented == sm.EDGES


@pytest.mark.parametrize(("source", "target"), list(itertools.product(S, S)))
def test_every_pair_of_statuses_is_allowed_or_refused_as_documented(source: S, target: S) -> None:
    if (source, target) in documented_edges():
        stage = {
            (S.RECEIVED, S.FAILED): Stage.INGEST,
            (S.READ, S.FAILED): Stage.EXTRACT,
            (S.EXTRACTED, S.FAILED): Stage.GROUND,
        }.get((source, target))
        duplicate_of = 7 if target is S.DUPLICATE else None
        sm.check_transition(source, target, failure_stage=stage, duplicate_of=duplicate_of)
    else:
        with pytest.raises(sm.IllegalTransition):
            sm.check_transition(source, target)


def test_exported_and_duplicate_are_final() -> None:
    for final in (S.EXPORTED, S.DUPLICATE):
        assert not [t for s, t in sm.EDGES if s is final], final
    for status in set(S) - {S.EXPORTED, S.DUPLICATE}:
        assert [t for s, t in sm.EDGES if s is status], status


def test_exported_documents_cannot_be_reopened() -> None:
    with pytest.raises(sm.IllegalTransition):
        sm.check_transition(S.EXPORTED, S.NEEDS_REVIEW)
    sm.check_transition(S.APPROVED, S.NEEDS_REVIEW)  # an approved one can be reopened


def test_every_status_can_be_reached_from_received() -> None:
    seen = {S.RECEIVED}
    queue = deque([S.RECEIVED])
    while queue:
        here = queue.popleft()
        for source, target in sm.EDGES:
            if source is here and target not in seen:
                seen.add(target)
                queue.append(target)
    assert seen == set(S)


def test_reprocessing_goes_back_to_received_or_read_from_review_rejected_or_failed() -> None:
    for source in (S.NEEDS_REVIEW, S.REJECTED, S.FAILED):
        for target in (S.RECEIVED, S.READ):
            assert sm.is_reprocess(source, target)
            sm.check_transition(source, target)
    assert not sm.is_reprocess(S.RECEIVED, S.READ)
    assert not sm.is_reprocess(S.APPROVED, S.NEEDS_REVIEW)


@pytest.mark.parametrize(
    ("source", "allowed"),
    [
        (S.RECEIVED, {Stage.INGEST, Stage.READ}),
        (S.READ, {Stage.EXTRACT}),
        (S.EXTRACTED, {Stage.GROUND, Stage.MATCH, Stage.CHECK}),
    ],
)
def test_failing_names_the_stage_that_failed(source: S, allowed: set[Stage]) -> None:
    for stage in Stage:
        if stage in allowed:
            sm.check_transition(source, S.FAILED, failure_stage=stage)
        else:
            with pytest.raises(sm.IllegalTransition, match="stage"):
                sm.check_transition(source, S.FAILED, failure_stage=stage)
    with pytest.raises(sm.IllegalTransition, match="stage"):
        sm.check_transition(source, S.FAILED)  # a stage is required


def test_a_stage_or_a_duplicate_pointer_only_goes_with_the_matching_status() -> None:
    with pytest.raises(sm.IllegalTransition, match="only"):
        sm.check_transition(S.RECEIVED, S.READ, failure_stage=Stage.READ)
    with pytest.raises(sm.IllegalTransition, match="only"):
        sm.check_transition(S.RECEIVED, S.READ, duplicate_of=3)
    with pytest.raises(sm.IllegalTransition, match="duplicate_of"):
        sm.check_transition(S.RECEIVED, S.DUPLICATE)
    sm.check_transition(S.NEEDS_REVIEW, S.DUPLICATE, duplicate_of=3)


def test_every_edge_has_a_short_machine_readable_trigger() -> None:
    triggers = [sm.trigger_for(s, t, stage) for (s, t) in sm.EDGES for stage in (None,)]
    assert all(re.fullmatch(r"[a-z_]{3,40}", t) for t in triggers)
    assert sm.trigger_for(S.RECEIVED, S.FAILED, Stage.READ) == "read_failed"
    assert sm.trigger_for(S.RECEIVED, S.FAILED, Stage.INGEST) == "ingest_failed"
    assert sm.trigger_for(S.NEEDS_REVIEW, S.APPROVED) == "approved"
