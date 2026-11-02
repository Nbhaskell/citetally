"""The evaluation harness: statistics, scoring, the world a run happens in, the runner and the
report. Invented records and fakes only: no model, no OCR program, no network. The held-out split
is never opened here."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from citetally import db
from citetally.config import Settings
from citetally.pipeline import Services
from citetally.providers import FakeProvider
from citetally.reading.ocr import FakeOcr
from tests.test_pipeline import GOOD, pdf
from tools.evaluation import report as reporting
from tools.evaluation import run as running
from tools.evaluation import stats
from tools.evaluation.score import BLOCKING, per_document, score_record, summarise
from tools.evaluation.world import order, seed
from tools.synthetic.facts import load_facts
from tools.synthetic.golden import Item, load_golden

TUNED = load_golden(split="tuned")


# --- statistics ---------------------------------------------------------------------------------


def test_wilson_interval_matches_known_values_and_stays_inside_0_and_1() -> None:
    low, high = stats.wilson(5, 10) or (0, 0)
    assert (round(low, 3), round(high, 3)) == (0.237, 0.763)
    low, high = stats.wilson(0, 10) or (1, 1)
    assert low == 0.0 and round(high, 3) == 0.278
    low, high = stats.wilson(10, 10) or (0, 0)
    assert high == pytest.approx(1.0) and round(low, 3) == 0.722
    assert stats.wilson(0, 0) is None


def test_the_pass_spread_needs_two_passes_and_uses_the_t_table() -> None:
    assert stats.t_halfwidth([0.9]) is None
    assert stats.t_halfwidth([1, 2, 3]) == pytest.approx(4.303 / 3**0.5)
    assert stats.t_halfwidth([0.5, 0.5, 0.5]) == 0.0


def test_the_bootstrap_is_repeatable_and_excludes_zero_only_for_a_consistent_change() -> None:
    steady = [0.1, 0.12, 0.08, 0.11, 0.09] * 8
    a, b = stats.paired_bootstrap(steady), stats.paired_bootstrap(steady)
    assert a == b and a is not None and a.excludes_zero and 0.09 < a.mean < 0.11
    noisy = [0.5, -0.5] * 20
    around_zero = stats.paired_bootstrap(noisy)
    assert around_zero is not None and not around_zero.excludes_zero
    assert stats.paired_bootstrap([]) is None


def test_a_difference_is_real_only_when_it_beats_both_the_spread_and_the_bootstrap() -> None:
    clear = [0.1] * 30 + [0.12] * 10
    assert stats.compare([0.10, 0.11, 0.105], clear).verdict == "real"
    # a clear bootstrap but passes that wobble more than the difference: unclear
    assert stats.compare([0.01, 0.30, -0.2], clear).verdict == "unclear"
    # passes agree, but the documents disagree about the direction: unclear
    assert stats.compare([0.02, 0.021, 0.019], [0.5, -0.45] * 20).verdict == "unclear"
    # neither
    assert stats.compare([0.5, -0.4, 0.0], [0.5, -0.5] * 20).verdict == "no difference found"


def test_one_pass_can_never_make_a_difference_real() -> None:
    result = stats.compare([0.1], [0.1] * 40)
    assert result.verdict == "unclear" and result.pass_spread is None


# --- scoring ------------------------------------------------------------------------------------


def perfect(item: Item, **changes: Any) -> dict[str, Any]:
    truth = item.truth
    fields: dict[str, Any] = dict(truth.printed)
    fields["lines"] = [dict(line.printed) for line in truth.lines]
    record = {
        "id": item.id,
        "condition": item.condition,
        "split": item.split,
        "status": "needs_review",
        "failure_stage": None,
        "seconds": 6.0,
        "page_count": 2,
        "context_missing": False,
        "extraction": {"fields": fields, "input_tokens": 900, "output_tokens": 300},
        "entry": {
            "entry_type": truth.entry_type,
            "vendor_golden_id": None if item.vendor_id.startswith("X") else item.vendor_id,
            "entry_date": truth.entry_date,
            "currency": truth.currency,
            "subtotal_minor": truth.subtotal_minor,
            "tax_total_minor": truth.tax_total_minor,
            "shipping_minor": truth.shipping_minor,
            "discount_minor": truth.discount_minor,
            "total_minor": truth.total_minor,
        },
        "evidence": [{"field": "total", "line": False, "printed_text": "x", "found": True}],
        "checks": [
            {"code": code, "blocking": True, "passed": code not in item.expected_checks}
            for code in (*BLOCKING, "DATE_SANITY", "AMOUNT_OUTLIER")
        ],
    }
    record.update(changes)
    return record


def first(planted: bool) -> Item:
    return next(i for i in TUNED if bool(i.planted) == planted)


def test_a_perfect_clean_record_scores_everything_right() -> None:
    item = first(planted=False)
    score = score_record(perfect(item), item)
    assert score["header_right"] == score["header_printed"] > 0
    assert score["line_f1"] == 1.0 and score["header_invented"] == 0
    assert set(score["money"].values()) == {"right"}
    assert score["vendor_right"] and score["date_right"] and score["currency_right"]
    assert score["planted"] == [] and not score["clean_alarm"] and score["failed_checks"] == []


def test_a_planted_problem_is_caught_when_every_expected_check_fails() -> None:
    item = first(planted=True)
    score = score_record(perfect(item), item)
    assert score["planted"] == [item.planted[0].kind]
    assert score["caught"] and score["caught_codes"] == sorted(item.expected_checks)
    assert score["collateral"] == []
    missed = perfect(item)
    for check in missed["checks"]:
        check["passed"] = True
    assert not score_record(missed, item)["caught"]


def test_other_checks_failing_on_a_planted_document_are_collateral_not_false_alarms() -> None:
    item = first(planted=True)
    record = perfect(item)
    for check in record["checks"]:
        if check["code"] == "DATE_SANITY":
            check["passed"] = False
    score = score_record(record, item)
    assert score["collateral"] == ["DATE_SANITY"] and not score["clean_alarm"]


def test_a_blocking_check_failing_on_a_clean_document_is_a_false_alarm_a_warning_is_not() -> None:
    item = first(planted=False)
    record = perfect(item)
    for check in record["checks"]:
        if check["code"] == "DATE_SANITY":
            check["passed"] = False
    assert not score_record(record, item)["clean_alarm"]
    for check in record["checks"]:
        if check["code"] == "TOTAL_MATCH":
            check["passed"] = False
    assert score_record(record, item)["clean_alarm"]


def test_a_line_with_no_quantity_is_wrong_strictly_but_right_when_quantity_is_ignored() -> None:
    item = next(i for i in TUNED if i.truth.lines and not i.planted)
    record = perfect(item)
    for line in record["extraction"]["fields"]["lines"]:
        line["quantity"] = None
    score = score_record(record, item)
    assert score["lines_right"] == 0 and score["line_f1"] == 0.0
    assert score["lines_core_right"] == len(item.truth.lines)
    summary = summarise([score])
    assert summary["line_f1"] == 0.0 and summary["line_core_f1"] == 1.0


def test_a_clean_alarm_from_grounding_alone_is_counted_apart() -> None:
    item = first(planted=False)
    record = perfect(item)
    for check in record["checks"]:
        if check["code"] == "VALUE_IN_DOCUMENT":
            check["passed"] = False
    score = score_record(record, item)
    assert score["clean_alarm"] and not score["clean_alarm_ungrounded"]
    summary = summarise([score])
    assert summary["clean_any_blocking_alarm"]["k"] == 1
    assert summary["clean_alarm_without_value_in_document"]["k"] == 0


def test_a_failed_document_counts_every_printed_field_as_wrong() -> None:
    item = first(planted=False)
    failed = perfect(item, status="failed", extraction=None, entry=None, checks=[])
    score = score_record(failed, item)
    assert score["header_right"] == 0 and score["header_printed"] > 0
    assert score["lines_predicted"] == 0 and score["lines_right"] == 0
    assert not score["vendor_right"] or item.vendor_id.startswith("X")


def test_a_duplicate_whose_original_is_not_in_the_run_is_left_out_of_the_check_metrics() -> None:
    item = next(i for i in TUNED if i.expected_duplicate_of)
    record = perfect(item, context_missing=True)
    score = score_record(record, item)
    assert score["excluded"] and score["planted"] == [] and not score["clean_alarm"]
    summary = summarise([score])
    assert summary["planted_recall"]["n"] == 0 and summary["clean_documents"] == 0
    assert per_document([score])[item.id]["planted_caught"] is None
    assert per_document([score])[item.id]["clean_alarm"] is None


def test_money_is_compared_as_minor_units_after_parsing() -> None:
    item = next(i for i in TUNED if i.truth.tax_total_minor is not None and not i.planted)
    record = perfect(item)
    assert item.truth.tax_total_minor is not None
    record["entry"]["tax_total_minor"] = item.truth.tax_total_minor + 1
    record["entry"]["shipping_minor"] = 500 if item.truth.shipping_minor is None else None
    money = score_record(record, item)["money"]
    assert money["tax_total"] == "wrong"
    assert money["shipping"] in {"invented", "missing"}


def test_the_summary_reports_rates_with_intervals_and_the_numbers_behind_them() -> None:
    clean = [i for i in TUNED if not i.planted][:6]
    planted = [i for i in TUNED if i.planted][:4]
    scores = [score_record(perfect(i), i) for i in [*clean, *planted]]
    # one clean document raises a blocking alarm; one planted problem is missed
    scores[0]["clean_alarm"] = True
    scores[0]["failed_checks"] = ["TOTAL_MATCH"]
    scores[-1]["caught"] = False
    scores[-1]["caught_codes"] = []
    summary = summarise(scores)
    assert summary["documents"] == 10
    assert (summary["planted_recall"]["k"], summary["planted_recall"]["n"]) == (3, 4)
    assert summary["planted_recall"]["rate"] == 0.75
    low, high = summary["planted_recall"]["low"], summary["planted_recall"]["high"]
    assert 0 < low < 0.75 < high < 1
    assert (summary["clean_any_blocking_alarm"]["k"], summary["clean_documents"]) == (1, 6)
    assert summary["false_alarm_by_check"]["TOTAL_MATCH"]["k"] == 1
    assert summary["header_field_exact"]["rate"] == 1.0 and summary["line_f1"] == 1.0
    assert summary["seconds_per_page_median"] == 3.0
    assert summary["input_tokens_mean"] == 900


def test_nothing_in_the_scorer_opens_the_sealed_split() -> None:
    with pytest.raises(PermissionError):
        load_golden(split="heldout")


# --- the world a run happens in ------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.migrate(connection)
    db.seed_categories(connection)
    return connection


def test_originals_come_before_the_documents_that_copy_them() -> None:
    items = list(reversed(TUNED))
    ordered = order(items)
    seen: set[str] = set()
    for item in ordered:
        if item.expected_duplicate_of:
            assert item.expected_duplicate_of in seen
        seen.add(item.id)
    assert len(ordered) == len(items)


def test_the_world_lists_the_known_vendors_only_and_gives_each_earlier_approved_entries(
    conn: sqlite3.Connection,
) -> None:
    facts = load_facts()
    world = seed(conn, facts, TUNED, min_history=5)
    assert (
        world.vendors
        == len(facts.vendors)
        == conn.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
    )
    names = {r[0] for r in conn.execute("SELECT name FROM vendors")}
    assert not names & {v.name for v in facts.unlisted_vendors}
    assert sorted(world.vendor_golden_id.values()) == sorted(v.id for v in facts.vendors)
    rows = conn.execute(
        "SELECT e.invoice_number, e.entry_date, d.status FROM entries e "
        "JOIN documents d ON d.id = e.document_id"
    ).fetchall()
    assert len(rows) == world.history_entries > 0
    assert {r["status"] for r in rows} == {"approved"}
    assert all(r["invoice_number"] is None and r["entry_date"] is None for r in rows)
    per_group = conn.execute(
        "SELECT COUNT(*) FROM entries GROUP BY vendor_id, currency, entry_type"
    ).fetchall()
    assert min(r[0] for r in per_group) >= 5


def test_history_is_built_only_from_documents_without_planted_problems(
    conn: sqlite3.Connection,
) -> None:
    clean_only = [i for i in TUNED if not i.planted]
    a = seed(conn, load_facts(), TUNED, min_history=1)
    other = db.connect(":memory:")
    db.migrate(other)
    db.seed_categories(other)
    b = seed(other, load_facts(), clean_only, min_history=1)
    assert a.history_entries == b.history_entries
    other.close()


# --- the runner, on fakes ------------------------------------------------------------------------


def item_for(path: Path, **changes: Any) -> Item:
    base: dict[str, Any] = json.loads(TUNED[0].model_dump_json())
    base.update(
        {
            "id": "T-test-1",
            "file": str(path),
            "condition": "clean_pdf",
            "source_kind": "digital_pdf",
            "planted": [],
            "expected_checks": [],
            "expected_duplicate_of": None,
            "vendor_id": "X99",
        }
    )
    base.update(changes)
    return Item.model_validate(base)


def fake_services(settings: Settings, replies: list[Any]) -> Services:
    return Services(
        settings=settings,
        ocr=FakeOcr(),
        provider=FakeProvider(replies),
        isolate=False,
        today=date(2026, 6, 15),
    )


def test_the_runner_saves_what_the_pipeline_stored_and_resumes_without_repeating_work(
    tmp_path: Path,
) -> None:
    source = tmp_path / "a.pdf"
    source.write_bytes(pdf())
    item = item_for(source)
    settings = Settings(_env_file=None, CITETALLY_DATA_DIR=str(tmp_path / "data"))
    services = fake_services(settings, [GOOD])
    out = tmp_path / "out"
    kwargs: dict[str, Any] = {
        "items": [item],
        "history_items": [item],
        "facts": load_facts(),
        "settings": settings,
        "work_dir": tmp_path / "work",
        "out_dir": out,
        "meta": {"variant": "baseline", "run_id": "t"},
        "log": lambda *a, **k: None,
    }
    records = running.run(services=services, **kwargs)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "needs_review" and record["page_count"] == 1
    assert record["extraction"]["fields"]["invoice_number"] == "INV-20417"
    assert record["entry"]["total_minor"] == 15200 and record["entry"]["category"] is not None
    assert {c["code"] for c in record["checks"]} >= {"TOTAL_MATCH", "UNKNOWN_VENDOR"}
    unknown = next(c for c in record["checks"] if c["code"] == "UNKNOWN_VENDOR")
    assert unknown["passed"] is False and unknown["blocking"] is True
    assert record["evidence"] and all(isinstance(e["found"], bool) for e in record["evidence"])
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["variant"] == "baseline" and meta["documents"] == 1 and "records_sha256" in meta
    # a second call finds the record and asks the model nothing
    again = fake_services(settings, [])
    resumed = running.run(services=again, **kwargs)
    assert [r["id"] for r in resumed] == ["T-test-1"]
    assert isinstance(again.provider, FakeProvider) and again.provider.calls == []


def test_the_held_out_split_stays_sealed_without_the_flag_and_after_one_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(running, "RUNS", tmp_path)
    monkeypatch.setattr(running, "HELDOUT_LOCK", tmp_path / "HELDOUT_RUN.lock")
    assert running.main(["--split", "heldout"]) == 2
    assert not (tmp_path / "HELDOUT_RUN.lock").exists()
    assert running.main(["--split", "heldout", "--confirm-heldout-once", "--limit", "3"]) == 2
    (tmp_path / "HELDOUT_RUN.lock").write_text("heldout-baseline-p1", encoding="utf-8")
    assert (
        running.main(["--split", "heldout", "--confirm-heldout-once", "--variant", "thinking"]) == 2
    )


def test_the_sealed_split_stays_sealed_without_its_own_flag_and_after_one_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(running, "RUNS", tmp_path)
    monkeypatch.setattr(running, "SEALED_LOCK", tmp_path / "SEALED_RUN.lock")
    assert running.main(["--split", "sealed"]) == 2
    assert running.main(["--split", "sealed", "--confirm-heldout-once"]) == 2  # the other flag
    assert not (tmp_path / "SEALED_RUN.lock").exists()
    assert running.main(["--split", "sealed", "--confirm-sealed-once", "--limit", "3"]) == 2
    (tmp_path / "SEALED_RUN.lock").write_text("sealed-baseline-p1", encoding="utf-8")
    assert (
        running.main(["--split", "sealed", "--confirm-sealed-once", "--variant", "thinking"]) == 2
    )


def test_the_new_splits_load_with_their_own_business_and_the_sealed_one_only_on_purpose() -> None:
    from tools.evaluation.suites import load_suite

    dev2 = load_suite("dev2")
    assert (
        len(dev2.items) == 100
        and dev2.facts.business.name != load_suite("tuned").facts.business.name
    )
    with pytest.raises(PermissionError):
        load_suite("sealed")
    with pytest.raises(PermissionError):
        load_suite("heldout")
    with pytest.raises(ValueError):
        load_suite("nonsense")


def test_variants_only_change_settings_and_all_of_them_are_valid() -> None:
    for name, env in running.VARIANTS.items():
        settings = Settings(_env_file=None, **env)  # type: ignore[arg-type]
        assert settings.model_provider == "ollama", name
    forced = Settings(_env_file=None, **running.VARIANTS["forced_ocr"])  # type: ignore[arg-type]
    assert forced.text_layer_min_chars >= 10**9
    thinking = Settings(_env_file=None, **running.VARIANTS["thinking"])  # type: ignore[arg-type]
    assert thinking.enable_thinking and thinking.extract_max_tokens > 2000
    image = Settings(_env_file=None, **running.VARIANTS["text_and_image"])  # type: ignore[arg-type]
    assert image.extract_mode == "text_and_image" and image.vision_model


# --- the report ----------------------------------------------------------------------------------


def write_run(root: Path, variant: str, number: int, items: list[Item], damage: int = 0) -> None:
    folder = root / f"tuned-{variant}-p{number}"
    folder.mkdir(parents=True)
    meta = {
        "run_id": folder.name, "split": "tuned", "variant": variant, "commit": "abc123def456",
        "tree_changed": False, "golden_file": "eval/golden/citetally_v1.json",
        "golden_sha256": "f" * 64, "provider": "ollama", "text_model": "qwen3:8b",
        "temperature": 0.0, "seed": 0, "prompt_version": "extract-v3", "ocr_engine": "tesseract",
        "tesseract": "tesseract 5", "machine": "test", "vendors_seeded": 16,
        "history_entries": 100, "history_padded": 3,
    }  # fmt: skip
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    lines = []
    for index, item in enumerate(items):
        record = perfect(item)
        if index < damage:  # the first few documents lose their total
            record["extraction"]["fields"]["total"] = None
        lines.append(json.dumps(record))
    (folder / "records.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_the_report_scores_saved_runs_compares_settings_and_lists_documents_to_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reporting, "RUNS", tmp_path)
    items = TUNED[:40]
    for number in (1, 2):
        write_run(tmp_path, "baseline", number, items)
        write_run(tmp_path, "forced_ocr", number, items, damage=12)
    built = reporting.build("tuned")
    assert set(built["variants"]) == {"baseline", "forced_ocr"}
    baseline = built["variants"]["baseline"]["passes"][1]["all"]
    assert baseline["documents"] == 40 and baseline["header_field_exact"]["rate"] == 1.0
    comparison = built["comparisons"]["forced_ocr"]
    assert comparison["documents"] == 40 and comparison["passes"] == [1, 2]
    header = comparison["header_accuracy"]
    assert header["difference"] < 0 and header["verdict"] == "real"
    assert comparison["line_f1"]["verdict"] == "no difference found"
    text = reporting.render(built)
    headings = [
        "# Evaluation: tuned split",
        "## Provenance",
        "## Headline numbers, baseline",
        "## Planted problems caught, by check code",
        "## False alarms on clean documents",
        "## Comparing settings with the baseline",
        "## What this cannot tell you",
        "## Reading list",
    ]
    for heading in headings:
        assert heading in text
    assert "(worse)" in text and "95% Wilson interval" in text
    assert "Invented documents only" in text


def test_a_report_needs_a_baseline_and_the_held_out_report_needs_the_one_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reporting, "RUNS", tmp_path)
    write_run(tmp_path, "forced_ocr", 1, TUNED[:5])
    with pytest.raises(SystemExit):
        reporting.build("tuned")
    monkeypatch.setattr(reporting, "HELDOUT_LOCK", tmp_path / "none.lock")
    assert reporting.main(["--name", "x", "--split", "heldout"]) == 2
