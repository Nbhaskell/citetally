"""The scorer and report: saved runs in, tables out. It never calls the model or any program.

    python -m tools.evaluation.report --name dev
    python -m tools.evaluation.report --name heldout --split heldout

Reads every run of the split under `eval/runs/`, scores each document against the golden truth,
and writes `eval/reports/eval_<name>.json` and `eval_<name>.md`. A setting other than the baseline
is compared with the baseline on the documents both ran, with the two checks of `stats.py`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tools.evaluation.run import HELDOUT_LOCK, ROOT, RUNS, read_records
from tools.evaluation.score import (
    BLOCKING,
    CONDITIONS,
    HEADLINES,
    group,
    per_document,
    score_record,
    summarise,
)
from tools.evaluation.stats import compare, t_halfwidth
from tools.synthetic.golden import Item, load_golden

REPORTS = ROOT / "eval" / "reports"
HEADLINE_TEXT = {
    "header_accuracy": "Header fields exact (share of printed fields read right)",
    "line_f1": "Line items F1",
    "planted_caught": "Planted problems caught (share of planted documents)",
    "clean_alarm": "Clean documents with a blocking false alarm",
}
# Which direction is better, so a verdict can say better or worse.
HIGHER_IS_BETTER = {
    "header_accuracy": True,
    "line_f1": True,
    "planted_caught": True,
    "clean_alarm": False,
}


# ---- loading and scoring -----------------------------------------------------------------------


def load_runs(split: str) -> dict[str, dict[int, dict[str, Any]]]:
    """{variant: {pass number: {"meta": ..., "records": {...}}}} for every saved run of a split."""
    found: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for meta_file in sorted(RUNS.glob(f"{split}-*/meta.json")):
        name = meta_file.parent.name
        if "-first" in name:  # a few documents tried out, not a run to report
            continue
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        records = read_records(meta_file.parent / "records.jsonl")
        found[meta["variant"]][_pass_of(name)] = {"meta": meta, "records": records, "name": name}
    return found


def _pass_of(name: str) -> int:
    token = next(part for part in name.split("-") if part.startswith("p") and part[1:].isdigit())
    return int(token[1:])


def score_run(records: dict[str, dict[str, Any]], items: dict[str, Item]) -> list[dict[str, Any]]:
    return [score_record(records[i], items[i]) for i in items if i in records]


# ---- formatting --------------------------------------------------------------------------------


def pct(rate: dict[str, Any] | float | None, *, interval: bool = True) -> str:
    if rate is None:
        return "–"
    if isinstance(rate, float):
        return f"{rate * 100:.1f}%"
    if rate["rate"] is None:
        return "–"
    text = f"{rate['rate'] * 100:.1f}%"
    if interval and rate["low"] is not None:
        text += f" ({rate['low'] * 100:.0f}–{rate['high'] * 100:.0f})"
    return text


def table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


# ---- comparing settings ------------------------------------------------------------------------


def _mean(values: Sequence[float | None]) -> float | None:
    real = [v for v in values if v is not None]
    return statistics.fmean(real) if real else None


def compare_variants(
    baseline: dict[int, list[dict[str, Any]]], other: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Each headline measure, other minus baseline, on the documents both ran in every pass."""
    shared_passes = sorted(set(baseline) & set(other))
    result: dict[str, Any] = {"passes": shared_passes}
    docs_each = {p: per_document(baseline[p]) for p in shared_passes}
    docs_other = {p: per_document(other[p]) for p in shared_passes}
    common = (
        set.intersection(*(set(docs_each[p]) & set(docs_other[p]) for p in shared_passes))
        if shared_passes
        else set()
    )
    result["documents"] = len(common)
    for measure in HEADLINES:
        pass_diffs: list[float] = []
        per_doc: dict[str, list[float]] = defaultdict(list)
        for p in shared_passes:
            a = [v for i in sorted(common) if (v := docs_each[p][i][measure]) is not None]
            b = [v for i in sorted(common) if (v := docs_other[p][i][measure]) is not None]
            if a and b:
                pass_diffs.append(statistics.fmean(b) - statistics.fmean(a))
            for i in common:
                x, y = docs_each[p][i][measure], docs_other[p][i][measure]
                if x is not None and y is not None:
                    per_doc[i].append(y - x)
        doc_diffs = [statistics.fmean(v) for v in per_doc.values()]
        c = compare(pass_diffs, doc_diffs)
        result[measure] = {
            "difference": round(c.difference, 4),
            "verdict": c.verdict,
            "documents": len(doc_diffs),
            "bootstrap_low": None if c.bootstrap is None else round(c.bootstrap.low, 4),
            "bootstrap_high": None if c.bootstrap is None else round(c.bootstrap.high, 4),
            "pass_spread": None if c.pass_spread is None else round(c.pass_spread, 4),
            "detectable": None if c.detectable is None else round(c.detectable, 4),
        }
    return result


# ---- the report --------------------------------------------------------------------------------


def build(split: str) -> dict[str, Any]:
    items_list = load_golden(split=split, unseal_heldout=split == "heldout")
    items = {i.id: i for i in items_list}
    runs = load_runs(split)
    if "baseline" not in runs:
        raise SystemExit(f"There is no baseline run of the {split} split under eval/runs/.")
    scored: dict[str, dict[int, list[dict[str, Any]]]] = {
        variant: {p: score_run(r["records"], items) for p, r in passes.items()}
        for variant, passes in runs.items()
    }
    report: dict[str, Any] = {"split": split, "variants": {}, "comparisons": {}}
    for variant, passes in scored.items():
        by_pass = {}
        for number, scores in sorted(passes.items()):
            by_pass[number] = {
                "documents": len(scores),
                "all": summarise(scores),
                "by_condition": {
                    c: summarise(s) for c, s in group(scores, lambda x: x["condition"]).items()
                },
                "by_family": {
                    f: summarise(s) for f, s in sorted(group(scores, lambda x: x["family"]).items())
                },
            }
        report["variants"][variant] = {
            "meta": runs[variant][min(runs[variant])]["meta"],
            "passes": by_pass,
            "headline_by_pass": {
                m: [_headline(passes[p], m) for p in sorted(passes)] for m in HEADLINES
            },
        }
    if len(scored) > 1:
        for variant in scored:
            if variant != "baseline":
                report["comparisons"][variant] = compare_variants(
                    scored["baseline"], scored[variant]
                )
    report["reading_list"] = reading_list(scored["baseline"][min(scored["baseline"])], items)
    return report


def _headline(scores: list[dict[str, Any]], measure: str) -> float | None:
    return _mean(list(v[measure] for v in per_document(scores).values()))


def reading_list(scores: list[dict[str, Any]], items: dict[str, Item]) -> dict[str, list[str]]:
    """Documents worth reading by hand, as ids with a few words: not a failure count."""
    failed = [s["id"] for s in scores if s["status"] == "failed"]
    missed = [
        f"{s['id']} ({s['planted'][0]}, {s['condition']})"
        for s in scores
        if s["planted"] and not s["caught"]
    ]
    alarms = [
        f"{s['id']} ({', '.join(c for c in s['failed_checks'] if c in BLOCKING)}; {s['condition']})"
        for s in scores
        if s["clean_alarm"]
    ]
    invented = [s["id"] for s in scores if s["header_invented"]]
    return {
        "failed_to_process": failed,
        "planted_problem_missed": missed,
        "false_alarm_on_clean_document": alarms,
        "header_value_invented": invented,
    }


def render(report: dict[str, Any]) -> str:
    split = report["split"]
    baseline = report["variants"]["baseline"]
    first = baseline["passes"][min(baseline["passes"])]
    meta = baseline["meta"]
    out: list[str] = [f"# Evaluation: {split} split", ""]
    out.append(
        "Invented documents only (all vendors, invoices and amounts are made up). "
        "Numbers are from saved runs under `eval/runs/`; this report was made from them without "
        "calling the model."
    )
    out += ["", "## Provenance", ""]
    out.append(
        table(
            ["", ""],
            [
                [
                    "Commit",
                    f"`{meta['commit'][:10]}`"
                    + (" (tree had changes)" if meta["tree_changed"] else ""),
                ],
                ["Golden set", f"`{meta['golden_file']}` sha256 `{meta['golden_sha256'][:16]}…`"],
                [
                    "Model",
                    f"{meta['provider']} / {meta['text_model']}, temperature {meta['temperature']}, seed {meta['seed']}",
                ],
                ["Prompt version", meta["prompt_version"]],
                ["OCR", f"{meta['ocr_engine']} ({meta['tesseract']})"],
                ["Machine", meta["machine"]],
                ["Documents", f"{first['documents']} ({split})"],
                [
                    "Passes per setting",
                    ", ".join(f"{v}: {len(d['passes'])}" for v, d in report["variants"].items()),
                ],
                [
                    "Vendors on the list / earlier entries",
                    f"{meta.get('vendors_seeded')} / {meta.get('history_entries')} ({meta.get('history_padded')} repeated to reach the minimum history)",
                ],
            ],
        )
    )

    out += ["", "## Headline numbers, baseline", ""]
    rows = []
    for name in (*CONDITIONS, "all"):
        s = first["all"] if name == "all" else first["by_condition"].get(name)
        if not s:
            continue
        rows.append(
            [
                name.replace("_", " "),
                str(s["documents"]),
                str(s["failed"]),
                pct(s["header_field_exact"]),
                pct(s["money_exact"]),
                "–" if s["line_f1"] is None else f"{s['line_f1'] * 100:.1f}%",
                pct(s["planted_recall"]),
                pct(s["clean_any_blocking_alarm"]),
                pct(s["values_found"], interval=False),
            ]
        )
    out.append(
        table(
            ["Condition", "Docs", "Failed", "Header fields exact", "Money exact", "Line F1",
             "Planted caught", "Clean docs with a blocking false alarm", "Values found on page"],
            rows,
        )
    )  # fmt: skip
    out.append("")
    out.append(
        "Percentages show the 95% Wilson interval in brackets. A document that failed counts every printed field as wrong."
    )

    out += ["", "## Header fields, baseline (all conditions)", ""]
    rows = [
        [name, pct(v), str(v["wrong"]), str(v["missing"]), str(v["invented"])]
        for name, v in first["all"]["header_by_field"].items()
    ]
    out.append(table(["Field", "Exact", "Wrong", "Missing", "Invented"], rows))

    out += ["", "## Planted problems caught, by check code", ""]
    rows = [[code, pct(v)] for code, v in first["all"]["planted_recall_by_code"].items()]
    out.append(table(["Check", "Caught"], rows))
    out += ["", "By kind of problem:", ""]
    rows = [[kind, pct(v)] for kind, v in first["all"]["planted_recall_by_kind"].items()]
    out.append(table(["Planted kind", "Caught"], rows))
    collateral = first["all"]["collateral_alarms_on_planted"]
    if collateral:
        out += [
            "",
            "Other checks that also failed on planted documents: "
            + ", ".join(f"{k} ×{v}" for k, v in collateral.items())
            + ".",
        ]

    out += ["", "## False alarms on clean documents, by blocking check", ""]
    clean = first["all"]["clean_documents"]
    rows = [[code, pct(first["all"]["false_alarm_by_check"][code])] for code in BLOCKING]
    out.append(table([f"Check (of {clean} clean documents)", "Failing"], rows))

    out += ["", "## Speed and size, baseline", ""]
    rows = [
        [
            name.replace("_", " "),
            "–" if s["seconds_per_page_median"] is None else f"{s['seconds_per_page_median']} s",
            "–" if s["input_tokens_mean"] is None else str(s["input_tokens_mean"]),
            "–" if s["output_tokens_mean"] is None else str(s["output_tokens_mean"]),
        ]
        for name, s in [*first["by_condition"].items(), ("all", first["all"])]
    ]
    out.append(
        table(
            ["Condition", "Median seconds per page", "Input tokens (mean)", "Output tokens (mean)"],
            rows,
        )
    )

    out += ["", "## Run-to-run spread", ""]
    rows = []
    for variant, data in report["variants"].items():
        if len(data["passes"]) < 2:
            continue
        for measure, values in data["headline_by_pass"].items():
            real = [v for v in values if v is not None]
            spread = t_halfwidth(real)
            rows.append(
                [
                    variant,
                    HEADLINE_TEXT[measure],
                    ", ".join(f"{v * 100:.2f}%" for v in real),
                    "–" if spread is None else f"±{spread * 100:.2f} points",
                ]
            )
    out.append(
        table(["Setting", "Measure", "Each pass", "95% t-interval"], rows)
        if rows
        else "Only one pass of each setting was run, so the spread between passes could not be measured."
    )

    if report["comparisons"]:
        out += ["", "## Comparing settings with the baseline", ""]
        out.append(
            "A difference is called **real** only when it is larger than the spread between passes "
            "and a paired bootstrap over documents excludes zero. One of the two is **unclear**. "
            "Neither is **no difference found**: that is the size the test could not separate from noise, "
            "not proof of no effect."
        )
        for variant, comp in report["comparisons"].items():
            out += [
                "",
                f"### {variant} against baseline ({comp['documents']} documents, {len(comp['passes'])} pass(es))",
                "",
            ]
            rows = []
            for measure in HEADLINES:
                c = comp[measure]
                good = HIGHER_IS_BETTER[measure]
                direction = (
                    ""
                    if c["verdict"] != "real"
                    else (" (better)" if (c["difference"] > 0) == good else " (worse)")
                )
                rows.append(
                    [
                        HEADLINE_TEXT[measure],
                        f"{c['difference'] * 100:+.2f} points",
                        "–"
                        if c["bootstrap_low"] is None
                        else f"{c['bootstrap_low'] * 100:+.2f} to {c['bootstrap_high'] * 100:+.2f}",
                        "–" if c["pass_spread"] is None else f"±{c['pass_spread'] * 100:.2f}",
                        c["verdict"] + direction,
                    ]
                )
            out.append(
                table(["Measure", "Difference", "Bootstrap 95%", "Pass spread", "Verdict"], rows)
            )

    out += ["", "## What this cannot tell you", ""]
    out += [
        "- The documents are invented, with layouts and noise made by one generator. Real invoices are messier; handwriting and unusual formats are absent.",
        "- Truth is known by construction, which is cleaner than real labelling. Planted problems are one per document and of 12 kinds chosen in advance.",
        f"- {first['documents']} documents per setting. Where a condition has few documents, its interval is wide; read the brackets, not the point values.",
        "- One machine, one local model, one OCR engine. Speed will differ elsewhere.",
        "- The checks are given a vendor list and earlier approved entries built from the fact sheet and the golden file. Real history is messier. See the harness notes in `docs/DECISIONS.md`.",
        "- The model is run at temperature 0 with a fixed seed, so repeated passes are expected to be nearly identical. The spread between passes therefore says little about the spread between different documents, which is what the bootstrap measures.",
        "- A person who wrote the system also wrote the test documents, so they are unseen but not blind.",
    ]
    if split == "heldout":
        out.append(
            "- The held-out split was opened once, after the development numbers were frozen. It is now spent: any further change made after reading it would have to be tested on a new sealed set."
        )

    out += ["", "## Reading list", "", "Documents worth opening by hand (not a failure count):", ""]
    for name, ids in report["reading_list"].items():
        out.append(
            f"- **{name.replace('_', ' ')}** ({len(ids)}): " + (", ".join(ids) if ids else "none")
        )
    return "\n".join(out) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--name", default="dev", help="report name: eval_<name>.md and .json")
    parser.add_argument("--split", choices=["tuned", "heldout"], default="tuned")
    args = parser.parse_args(argv)
    if args.split == "heldout" and not HELDOUT_LOCK.exists():
        print("The held-out split has not been run, so there is nothing to score.")
        return 2
    report = build(args.split)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"eval_{args.name}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    text = render(report)
    (REPORTS / f"eval_{args.name}.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["Path", "build", "compare_variants", "load_runs", "render", "score_run"]
