"""Every evaluation number quoted in the README is the one in the saved report.

The reports (`eval/reports/eval_dev.json`, `eval_heldout.json`) are the source. If a report is made
again with different results, this fails until the README is corrected, so the README cannot drift
from the evidence.
"""

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (ROOT / "eval" / "reports" / f"eval_{name}.json").read_text(encoding="utf-8")
    )
    return data


DEV = load("dev")
HELD = load("heldout")


def first_pass(report: dict[str, Any], variant: str = "baseline") -> dict[str, Any]:
    passes = report["variants"][variant]["passes"]
    out: dict[str, Any] = passes[min(passes, key=int)]
    return out


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def header(report: dict[str, Any], condition: str | None, variant: str = "baseline") -> str:
    scope = first_pass(report, variant)
    block = scope["all"] if condition is None else scope["by_condition"][condition]
    return pct(block["header_field_exact"]["rate"])


def test_the_header_table_matches_the_reports() -> None:
    for condition in (None, "clean_pdf", "scan_light", "scan_heavy", "phone_photo"):
        for report in (DEV, HELD):
            assert header(report, condition) in README, (condition, header(report, condition))


@pytest.mark.parametrize("report", [DEV, HELD], ids=["development", "held-out"])
def test_the_all_documents_figures_match(report: dict[str, Any]) -> None:
    block = first_pass(report)["all"]
    for value in (
        block["money_exact"]["rate"],
        block["line_f1"],
        block["planted_recall"]["rate"],
        block["clean_any_blocking_alarm"]["rate"],
    ):
        assert pct(value) in README, value


def test_the_clean_pdf_line_scores_match() -> None:
    for report in (DEV, HELD):
        value = first_pass(report)["by_condition"]["clean_pdf"]["line_f1"]
        assert pct(value) in README, value


def test_the_text_and_image_and_forced_ocr_figures_match() -> None:
    image = first_pass(DEV, "text_and_image")["by_condition"]
    for condition in ("scan_heavy", "phone_photo"):
        assert pct(image[condition]["header_field_exact"]["rate"]) in README
    forced = first_pass(DEV, "forced_ocr")["by_condition"]["clean_pdf"]
    assert pct(forced["header_field_exact"]["rate"]) in README
    assert pct(forced["line_f1"]) in README


def test_the_thinking_figures_match() -> None:
    thinking = first_pass(DEV, "thinking")["by_condition"]["clean_pdf"]
    base = first_pass(DEV)["by_condition"]["clean_pdf"]
    assert pct(thinking["line_f1"]) in README and pct(base["line_f1"]) in README
    assert pct(thinking["planted_recall"]["rate"]) in README
    assert pct(base["planted_recall"]["rate"]) in README
    for block in (thinking, base):
        assert f"{block['seconds_per_page_median']:.1f}" in README


def test_the_sizes_quoted_match_the_reports() -> None:
    assert f"({first_pass(DEV)['documents']} documents)" in README
    assert f"{first_pass(HELD)['documents']} documents" in README
    assert f"{first_pass(HELD)['all']['planted_recall']['n']} planted problems" in README


def sealed_final() -> dict[str, Any]:
    passes = load("sealed")["variants"]["final"]["passes"]
    out: dict[str, Any] = passes[min(passes, key=int)]
    return out


def test_the_sealed_table_matches_the_sealed_report() -> None:
    sealed = sealed_final()
    rows = (
        ("Clean PDFs", "clean_pdf"),
        ("Light scans", "scan_light"),
        ("Heavy scans", "scan_heavy"),
        ("Phone photos", "phone_photo"),
    )
    for label, condition in rows:
        block = sealed["by_condition"][condition]
        row = (
            f"| {label} ({block['documents']}) "
            f"| {pct(block['header_field_exact']['rate'])} "
            f"| {pct(block['clean_any_blocking_alarm']['rate'])} |"
        )
        assert row in README, row
    block = sealed["all"]
    row = (
        f"| All ({sealed['documents']}) | {pct(block['header_field_exact']['rate'])} "
        f"| {pct(block['clean_any_blocking_alarm']['rate'])} |"
    )
    assert row in README, row


def test_the_other_sealed_figures_match() -> None:
    block = sealed_final()["all"]
    planted = block["planted_recall"]
    for text in (
        f"money exact {pct(block['money_exact']['rate'])}",
        f"line-item F1 {pct(block['line_f1'])}",
        f"planted problems caught {pct(planted['rate'])}",
        f"({planted['low'] * 100:.0f} to {planted['high'] * 100:.0f}%)",
        f"median {block['seconds_per_page_median']:.1f} seconds per page",
    ):
        assert text in README, text
    tax = block["planted_recall_by_kind"]["tax_mismatch"]
    assert f"{tax['k']} of {tax['n']} planted tax mismatches" in README
    injection = block["planted_recall_by_kind"]["injection_text"]
    assert f"{injection['k']} of {injection['n']} planted pieces of instruction-like text" in README
    value_in_document = block["false_alarm_by_check"]["VALUE_IN_DOCUMENT"]["rate"]
    assert f"({pct(value_in_document)} of clean documents)" in README


def test_the_pilot_figures_match_the_pilot_report() -> None:
    pilot = json.loads((ROOT / "eval" / "reports" / "pilot.json").read_text(encoding="utf-8"))
    for text in (
        f"{pilot['approved']} were approved",
        f"median review took {round(pilot['review_median'])} seconds",
        f"median typing took {round(pilot['typed_median'])} seconds",
        f"a ratio of {pilot['ratio']:.2f}",
        f"{len(pilot['wrong_core_approved_without_override'])} of the {pilot['approved']} approved",
        f"{len(pilot['wrong_core_approved_with_override'])} more held one with an override",
        f"{pilot['typed_with_errors']} of the {pilot['typed_total']} typed records",
    ):
        assert text in README, text


def stage2(name: str) -> dict[str, Any]:
    report = load(f"stage2_{name}")
    passes = report["variants"]["final"]["passes"]
    out: dict[str, Any] = passes[min(passes, key=int)]
    return out


def test_the_stage_2_numbers_match_the_stage_2_reports() -> None:
    for name in ("tuned", "dev2"):
        final = stage2(name)
        for condition in ("clean_pdf", "scan_light", "scan_heavy", "phone_photo"):
            assert pct(final["by_condition"][condition]["header_field_exact"]["rate"]) in README
        assert pct(final["all"]["clean_any_blocking_alarm"]["rate"]) in README
    assert (
        f"about {round(stage2('dev2')['all']['seconds_per_page_median'])} seconds per page"
        in README
    )


def sealed_run(name: str, variant: str) -> dict[str, Any]:
    passes = load(name)["variants"][variant]["passes"]
    out: dict[str, Any] = passes[min(passes, key=int)]
    return out


def test_the_sealed_comparison_table_matches_the_reports() -> None:
    runs = (
        ("Held-out (first system)", first_pass(HELD)),
        ("`sealed`", sealed_final()),
        ("`sealed2`", sealed_run("sealed2", "final")),
        ("`sealed3`", sealed_run("sealed3", "final_hybrid")),
    )
    for label, report in runs:
        block = report["all"]
        row = (
            f"| {label} | {report['documents']} "
            f"| {pct(block['header_field_exact']['rate'])} "
            f"| {pct(block['money_exact']['rate'])} "
            f"| {pct(block['line_f1'])} "
            f"| {pct(block['planted_recall']['rate'])} "
            f"| {pct(block['clean_any_blocking_alarm']['rate'])} |"
        )
        assert row in README, row


def test_the_sealed2_and_sealed3_figures_quoted_in_words_match() -> None:
    second = sealed_run("sealed2", "final")["all"]
    third = sealed_run("sealed3", "final_hybrid")
    block = third["all"]
    for kind, report, noun in (
        ("tax_mismatch", second, "tax mismatches"),
        ("injection_text", second, "instruction texts"),
        ("tax_mismatch", block, "tax mismatches"),
        ("injection_text", block, "instruction texts"),
    ):
        found = report["planted_recall_by_kind"][kind]
        assert f"{found['k']} of {found['n']} {noun}" in README, (kind, noun)
    heavy = third["by_condition"]["scan_heavy"]
    for text in (
        f"{pct(heavy['header_field_exact']['rate'])} of header fields exact",
        f"{pct(heavy['line_f1'])} line-item F1",
        f"{pct(heavy['clean_any_blocking_alarm']['rate'])} of clean documents blocked",
        f"found {pct(block['values_found']['rate'])} of returned values on the page",
        f"Median {block['seconds_per_page_median']:.1f} seconds per page",
        f"fails {pct(block['false_alarm_by_check']['VALUE_IN_DOCUMENT']['rate'])} of clean",
    ):
        assert text in README, text
