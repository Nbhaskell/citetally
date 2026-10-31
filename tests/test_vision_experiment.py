"""The vision experiment's decision rule, on invented summaries."""

from typing import Any

from tools import vision_experiment as vx


def summary(
    header: float, failed: int = 0, invented: int = 0, seconds: float = 20.0
) -> dict[str, Any]:
    return {
        "documents": 35,
        "failed": failed,
        "header_field_accuracy": header,
        "header_values_invented": invented,
        "header_documents_all_right": 0.0,
        "line_recall": 0.0,
        "grounding_coverage": 0.9,
        "seconds_per_document_median": seconds,
    }


def report(image: dict[str, Any], *others: dict[str, Any]) -> dict[str, Any]:
    text, vl = (others + (summary(0.40), summary(0.40)))[:2]
    return {
        "configs": {
            "text_model_text_only": {c: text for c in vx.CONDITIONS},
            "vl_text_only": {c: vl for c in vx.CONDITIONS},
            "vl_text_and_image": {c: image for c in vx.CONDITIONS},
        }
    }


def test_a_clear_gain_over_both_text_only_runs_enables_image_mode() -> None:
    result = vx.verdict(report(summary(0.55)))
    assert result["enable"] and result["gains"]["scan_heavy"] == 0.15


def test_a_gain_over_only_one_of_the_text_runs_is_not_enough() -> None:
    assert not vx.verdict(report(summary(0.55), summary(0.40), summary(0.50)))["enable"]


def test_a_gain_below_ten_points_is_not_enough() -> None:
    assert not vx.verdict(report(summary(0.49)))["enable"]


def test_more_failures_or_invented_values_or_slowness_each_block_it() -> None:
    assert not vx.verdict(report(summary(0.60, failed=1)))["enable"]
    assert not vx.verdict(report(summary(0.60, invented=1)))["enable"]
    assert not vx.verdict(report(summary(0.60, seconds=61.0)))["enable"]
    assert vx.verdict(report(summary(0.60, seconds=60.0)))["enable"]


def test_the_table_names_each_configuration_and_the_verdict() -> None:
    text = vx.render({**report(summary(0.55)), "verdict": vx.verdict(report(summary(0.55)))})
    assert "vl_text_and_image / phone_photo" in text and "ENABLE" in text
