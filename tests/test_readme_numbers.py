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
