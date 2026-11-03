"""The pilot (D-062, D-067): is reviewing faster than typing, and does review let wrong values through?

Run after the sealed run, on documents from the sealed set, in this order:

    prepare   pick 40 sealed documents (10 per condition), copy them under neutral names, and make a
              separate database seeded the way the sealed run was (vendor list, earlier entries)
    (you)     start the API and web on that database, upload `data/pilot/files/`, review each
              document in the app and approve, reject or set it aside. The app records the seconds.
    type      type the same 40 by hand, one at a time, with the clock running; writes `typed.jsonl`
    report    medians of both, the ratio, and every approved entry whose values differ from the
              answer key, with whether it carried an override

Everything lives under `data/pilot/` (git-ignored). The report is `eval/reports/pilot.md` and `.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from citetally import db
from citetally import repository as repo
from citetally.config import Settings
from citetally.dates import parse_date
from citetally.matching import normalize_name
from citetally.models import Decision
from citetally.money import parse_money
from tools.evaluation.suites import load_suite
from tools.evaluation.world import seed
from tools.synthetic.golden import Item

REPO = Path(__file__).resolve().parents[1]
PILOT = REPO / "data" / "pilot"
REPORTS = REPO / "eval" / "reports"
PER_CONDITION = 10
SEED = 7
CONDITIONS = ("clean_pdf", "scan_light", "scan_heavy", "phone_photo")


class _Candidate(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def condition(self) -> str: ...
    @property
    def expected_duplicate_of(self) -> str | None: ...


# ---- choosing the documents --------------------------------------------------------------------


def select(
    items: Sequence[_Candidate], per_condition: int = PER_CONDITION, seed_: int = SEED
) -> list[str]:
    """Document ids: `per_condition` of each condition, chosen and then shuffled with a fixed seed.

    Documents that copy another are left out: the pilot database holds only these documents, and a
    duplicate needs its original there (duplicate detection is measured by the sealed run).
    """
    rng = random.Random(seed_)
    chosen: list[str] = []
    for condition in CONDITIONS:
        pool = sorted(
            i.id for i in items if i.condition == condition and not i.expected_duplicate_of
        )
        if len(pool) < per_condition:
            raise ValueError(f"only {len(pool)} usable {condition} documents")
        chosen += rng.sample(pool, per_condition)
    rng.shuffle(chosen)
    return chosen


# ---- comparing with the answer key -------------------------------------------------------------

CORE = ("vendor", "invoice_number", "entry_date", "total", "lines")
OTHER = (
    "entry_type",
    "due_date",
    "po_number",
    "currency",
    "subtotal",
    "tax_total",
    "shipping",
    "discount",
)


def _same_text(a: str | None, b: str | None) -> bool:
    return " ".join((a or "").split()).casefold() == " ".join((b or "").split()).casefold()


def _decimal(text: str | None) -> Decimal | None:
    try:
        return None if text is None else Decimal(text.replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return None


def _same_number(a: str | None, b: str | None) -> bool:
    x, y = _decimal(a), _decimal(b)
    return x is not None and y is not None and x == y


def _minor_of(text: str | None) -> int | None:
    parsed = parse_money(text or "", "en-US", "USD")
    return None if parsed is None else int((parsed.value * 100).to_integral_value())


def _date_of(text: str | None) -> str | None:
    parsed = parse_date(text or "", "en-US")
    value = getattr(parsed, "value", parsed)
    return None if value is None else str(value)


def entry_differences(entry: Mapping[str, Any], truth: Any) -> list[str]:
    """Which values on an entry differ from the answer key (names from `CORE` and `OTHER`).

    `entry` holds the entry as stored: `vendor` (the chosen vendor's name), `invoice_number`,
    `entry_date`, `due_date`, `po_number`, `currency`, `entry_type`, the `*_minor` amounts, and
    `lines` with `description`, `quantity`, `unit_price`, `amount_minor`.
    """
    wrong: list[str] = []
    printed_vendor = truth.printed.get("vendor_name")
    vendor = normalize_name(entry.get("vendor") or "")
    if vendor not in {normalize_name(truth.vendor_name), normalize_name(printed_vendor or "")}:
        wrong.append("vendor")
    if not _same_text(entry.get("invoice_number"), truth.invoice_number):
        wrong.append("invoice_number")
    if entry.get("entry_date") != truth.entry_date:
        wrong.append("entry_date")
    if entry.get("total_minor") != truth.total_minor:
        wrong.append("total")
    lines = entry.get("lines") or []
    if len(lines) != len(truth.lines) or any(
        not _same_text(got.get("description"), want.description)
        or not _same_number(got.get("quantity"), want.quantity)
        or not _same_number(got.get("unit_price"), want.unit_price)
        or got.get("amount_minor") != want.amount_minor
        for got, want in zip(lines, truth.lines, strict=False)
    ):
        wrong.append("lines")
    for name in OTHER:
        column = (
            name if name in {"entry_type", "due_date", "po_number", "currency"} else f"{name}_minor"
        )
        if entry.get(column) != getattr(truth, column):
            wrong.append(name)
    return wrong


def typed_differences(typed: Mapping[str, Any], truth: Any) -> list[str]:
    """The same comparison for what was typed by hand (only the values `type` asks for)."""
    wrong: list[str] = []
    vendors = {
        normalize_name(truth.vendor_name),
        normalize_name(truth.printed.get("vendor_name", "")),
    }
    if normalize_name(typed.get("vendor") or "") not in vendors:
        wrong.append("vendor")
    if not _same_text(typed.get("invoice_number"), truth.invoice_number):
        wrong.append("invoice_number")
    if _date_of(typed.get("entry_date")) != truth.entry_date:
        wrong.append("entry_date")
    if _minor_of(typed.get("total")) != truth.total_minor:
        wrong.append("total")
    lines = typed.get("lines") or []
    if len(lines) != len(truth.lines) or any(
        not _same_text(got.get("description"), want.description)
        or not _same_number(got.get("quantity"), want.quantity)
        or not _same_number(got.get("unit_price"), want.unit_price)
        or _minor_of(got.get("amount")) != want.amount_minor
        for got, want in zip(lines, truth.lines, strict=False)
    ):
        wrong.append("lines")
    return wrong


def median(values: Sequence[float]) -> float | None:
    return None if not values else float(statistics.median(values))


# ---- prepare -----------------------------------------------------------------------------------


def prepare(force: bool = False) -> int:
    database = PILOT / "pilot.db"
    if database.exists() and not force:
        print(f"{database} already exists, so reviews may be in it. Nothing was changed.")
        print("Use --force only to throw the pilot away and start again.")
        return 1
    suite = load_suite("sealed", unseal=True)
    by_id = {i.id: i for i in suite.items}
    ids = select(suite.items)
    shutil.rmtree(PILOT, ignore_errors=True)
    (PILOT / "files").mkdir(parents=True)
    selection: list[dict[str, str]] = []
    for number, item_id in enumerate(ids, start=1):
        item = by_id[item_id]
        source = REPO / item.file
        name = f"p{number:02d}{source.suffix}"
        shutil.copyfile(source, PILOT / "files" / name)
        selection.append({"pilot": f"p{number:02d}", "id": item_id, "condition": item.condition})
    (PILOT / "selection.json").write_text(json.dumps(selection, indent=1), encoding="utf-8")

    conn = db.connect(str(database))
    db.migrate(conn)
    db.seed_categories(conn)
    world = seed(conn, suite.facts, suite.items, min_history=Settings().outlier_min_history)
    conn.close()
    print(f"Chose {len(ids)} documents ({PER_CONDITION} of each condition) in a shuffled order.")
    print(
        f"Pilot database: {database} ({world.vendors} vendors, {world.history_entries} earlier entries)."
    )
    print()
    print("Next, in two PowerShell windows from the repository root:")
    print(
        "  $env:CITETALLY_DB_PATH = 'data\\pilot\\pilot.db'; .\\.venv\\Scripts\\python.exe -m citetally"
    )
    print("  npm --prefix web run dev")
    print("Open http://127.0.0.1:5175, upload everything in data\\pilot\\files, wait until all are")
    print("read, then review them one at a time from the Inbox, approving, rejecting or setting")
    print(
        "aside each. Review all of them before you run the typing step, and do not open the files"
    )
    print("outside the app until then.")
    return 0


# ---- type --------------------------------------------------------------------------------------


def _ask(prompt: str) -> str:
    return input(prompt).strip()


def _read_typed() -> dict[str, dict[str, Any]]:
    path = PILOT / "typed.jsonl"
    if not path.exists():
        return {}
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return {row["pilot"]: row for row in rows}


def type_by_hand() -> int:
    selection = json.loads((PILOT / "selection.json").read_text(encoding="utf-8"))
    done = _read_typed()
    print("Type each document by hand. The clock runs from the moment you press Enter at the first")
    print(
        "prompt until you finish the last line. Lines are: description | quantity | unit price | amount."
    )
    print("Press Enter on an empty line to finish the lines. Type q at the first prompt to stop.")
    for number, row in enumerate(selection, start=1):
        if row["pilot"] in done:
            continue
        path = next((PILOT / "files").glob(f"{row['pilot']}.*"))
        if (
            _ask(
                f"\n[{number}/{len(selection)}] {path.name}. Enter to open it and start (q to stop): "
            ).lower()
            == "q"
        ):
            break
        if sys.platform == "win32":
            os.startfile(path)
        else:
            print(f"Open {path} yourself.")
        start = time.monotonic()
        vendor = _ask("Vendor: ")
        invoice_number = _ask("Invoice or receipt number (blank if none): ")
        entry_date = _ask("Date: ")
        lines: list[dict[str, str]] = []
        while text := _ask(f"Line {len(lines) + 1}: "):
            parts = [p.strip() for p in text.split("|")]
            parts += [""] * (4 - len(parts))
            lines.append(
                dict(
                    zip(("description", "quantity", "unit_price", "amount"), parts[:4], strict=True)
                )
            )
        total = _ask("Total: ")
        seconds = round(time.monotonic() - start, 1)
        record = {
            "pilot": row["pilot"],
            "seconds": seconds,
            "vendor": vendor,
            "invoice_number": invoice_number or None,
            "entry_date": entry_date,
            "total": total,
            "lines": lines,
        }
        with (PILOT / "typed.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        print(f"  {seconds} s")
    return 0


# ---- report ------------------------------------------------------------------------------------


def _stored_entry(conn: Any, document_id: int) -> dict[str, Any] | None:
    entry = repo.get_entry_for_document(conn, document_id)
    if entry is None:
        return None
    vendor = (
        repo.get_vendor(conn, entry.vendor_id).name if entry.vendor_id else entry.vendor_name_raw
    )
    data = {k: getattr(entry, k) for k in (
        "invoice_number", "entry_date", "due_date", "po_number", "currency",
        "subtotal_minor", "tax_total_minor", "shipping_minor", "discount_minor", "total_minor",
    )}  # fmt: skip
    data["entry_type"] = getattr(entry.entry_type, "value", entry.entry_type)
    data["vendor"] = vendor
    data["lines"] = [
        {
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "amount_minor": line.amount_minor,
        }
        for line in repo.list_lines(conn, entry.id)
    ]
    return data


def collect() -> dict[str, Any]:
    selection = json.loads((PILOT / "selection.json").read_text(encoding="utf-8"))
    by_id = {i.id: i for i in load_suite("sealed", unseal=True).items}
    typed = _read_typed()
    conn = db.connect(str(PILOT / "pilot.db"))
    rows: list[dict[str, Any]] = []
    for row in selection:
        item: Item = by_id[row["id"]]
        found = conn.execute(
            "SELECT id FROM documents WHERE original_filename LIKE ?", (f"{row['pilot']}.%",)
        ).fetchone()
        record: dict[str, Any] = {
            "pilot": row["pilot"],
            "id": row["id"],
            "condition": row["condition"],
        }
        if found is not None:
            document = repo.get_document(conn, found["id"])
            reviews = repo.list_reviews(conn, document.id)
            decided = [r for r in reviews if r.decision is not Decision.REOPEN]
            last = decided[-1] if decided else None
            record["status"] = document.status.value
            record["decision"] = None if last is None else last.decision.value
            record["review_seconds"] = None if last is None else last.review_seconds
            record["overrides"] = 0 if last is None else last.overrides
            record["edited"] = False if last is None else bool(last.edited)
            if document.status.value == "approved":
                stored = _stored_entry(conn, document.id)
                wrong = [] if stored is None else entry_differences(stored, item.truth)
                record["wrong_core"] = [w for w in wrong if w in CORE]
                record["wrong_other"] = [w for w in wrong if w in OTHER]
        if row["pilot"] in typed:
            record["typed_seconds"] = typed[row["pilot"]]["seconds"]
            record["typed_wrong"] = typed_differences(typed[row["pilot"]], item.truth)
        rows.append(record)
    conn.close()
    return summarise(rows)


def summarise(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    paired = [
        r
        for r in rows
        if r.get("decision") == "approve"
        and r.get("review_seconds") is not None
        and "typed_seconds" in r
    ]
    review = [float(r["review_seconds"]) for r in paired]
    typed = [float(r["typed_seconds"]) for r in paired]
    by_condition: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in paired:
        grouped[r["condition"]].append(r)
    for condition in CONDITIONS:
        group = grouped.get(condition, [])
        r_med = median([float(r["review_seconds"]) for r in group])
        t_med = median([float(r["typed_seconds"]) for r in group])
        by_condition[condition] = {
            "documents": len(group),
            "review_median": r_med,
            "typed_median": t_med,
            "ratio": None if not r_med or not t_med else r_med / t_med,
        }
    approved = [r for r in rows if r.get("status") == "approved"]
    wrong_approved = [r for r in approved if r.get("wrong_core")]
    r_med, t_med = median(review), median(typed)
    return {
        "documents": len(rows),
        "reviewed_and_typed": len(paired),
        "decisions": {
            d: sum(r.get("decision") == d for r in rows)
            for d in ("approve", "reject", "mark_duplicate")
        },
        "not_reviewed": [r["pilot"] for r in rows if r.get("decision") is None],
        "not_typed": [r["pilot"] for r in rows if "typed_seconds" not in r],
        "review_median": r_med,
        "typed_median": t_med,
        "ratio": None if not r_med or not t_med else r_med / t_med,
        "paired_ratio_median": median(
            [
                float(r["review_seconds"]) / float(r["typed_seconds"])
                for r in paired
                if r["typed_seconds"]
            ]
        ),
        "by_condition": by_condition,
        "approved": len(approved),
        "approved_with_override": sum(1 for r in approved if r["overrides"] > 0),
        "wrong_core_approved": len(wrong_approved),
        "wrong_core_approved_without_override": [
            r["pilot"] for r in wrong_approved if r["overrides"] == 0
        ],
        "wrong_core_approved_with_override": [
            r["pilot"] for r in wrong_approved if r["overrides"] > 0
        ],
        "wrong_other_approved": sum(1 for r in approved if r.get("wrong_other")),
        "typed_with_errors": sum(1 for r in rows if r.get("typed_wrong")),
        "typed_total": sum(1 for r in rows if "typed_seconds" in r),
        "rows": list(rows),
    }


def _seconds(value: float | None) -> str:
    return "–" if value is None else f"{value:.0f} s"


def render(s: Mapping[str, Any]) -> str:
    ratio = s["ratio"]
    out = [
        "# Pilot: reviewing against typing by hand",
        "",
        "Invented documents only, taken from the sealed set. One reviewer, the person who built the system.",
        "",
        "## Targets",
        "",
        "| Target | Result |",
        "|---|---|",
        "| 3. A document is finished in under half the time of typing it (median review / median typing under 0.5) | "
        + (
            "not measured"
            if ratio is None
            else f"**{ratio:.2f}** ({'met' if ratio < 0.5 else 'not met'}) on {s['reviewed_and_typed']} documents"
        )
        + " |",
        "| 4. No wrong value approved without a recorded override | "
        + (
            "not measured"
            if not s["approved"]
            else f"**{len(s['wrong_core_approved_without_override'])}** of {s['approved']} approved entries had a wrong value "
            f"and no override ({'met' if not s['wrong_core_approved_without_override'] else 'not met'}); "
            f"{len(s['wrong_core_approved_with_override'])} had one with an override"
        )
        + " |",
        "",
        "## Times",
        "",
        f"Median review {_seconds(s['review_median'])}, median typing {_seconds(s['typed_median'])}; median of the per-document ratios "
        + ("–" if s["paired_ratio_median"] is None else f"{s['paired_ratio_median']:.2f}")
        + ".",
        "",
        "| Condition | Documents | Review (median) | Typing (median) | Ratio |",
        "|---|---|---|---|---|",
    ]
    for condition, c in s["by_condition"].items():
        out.append(
            f"| {condition.replace('_', ' ')} | {c['documents']} | {_seconds(c['review_median'])} | {_seconds(c['typed_median'])} | "
            + ("–" if c["ratio"] is None else f"{c['ratio']:.2f}")
            + " |"
        )
    out += [
        "",
        "## Decisions and accuracy",
        "",
        f"- Of {s['documents']} documents: approved {s['decisions']['approve']}, rejected {s['decisions']['reject']}, "
        f"set aside as duplicate {s['decisions']['mark_duplicate']}; not reviewed: {', '.join(s['not_reviewed']) or 'none'}; "
        f"not typed: {', '.join(s['not_typed']) or 'none'}.",
        f"- Approved entries with an accepted check (override): {s['approved_with_override']} of {s['approved']}.",
        f"- Approved entries whose vendor, number, date, total or lines differ from the answer key: {s['wrong_core_approved']} "
        f"(without an override: {', '.join(s['wrong_core_approved_without_override']) or 'none'}; "
        f"with one: {', '.join(s['wrong_core_approved_with_override']) or 'none'}).",
        f"- Approved entries with another header value different from the key (due date, PO number, currency, subtotal, tax, "
        f"shipping, discount, type): {s['wrong_other_approved']}.",
        f"- Documents typed with at least one difference from the key: {s['typed_with_errors']} of {s['typed_total']}.",
        "",
        "## What this cannot tell you",
        "",
        "- One reviewer, who built the system and knows how it fails; a new user would likely be slower.",
        "- Review seconds are the time the review screen was open, including any pause. Typing seconds are from the first prompt to the last line.",
        "- The documents are invented. Typing was done in a console helper, not a spreadsheet. Documents that copy another were left out, so duplicate handling is not part of this.",
        "- 40 documents: read the per-condition rows as indications, not estimates.",
    ]
    return "\n".join(out) + "\n"


def report(name: str = "pilot") -> int:
    summary = collect()
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{name}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (REPORTS / f"{name}.md").write_text(render(summary), encoding="utf-8", newline="\n")
    print(render(summary))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="choose the documents and make the pilot database")
    p.add_argument("--force", action="store_true", help="throw the pilot away and start again")
    sub.add_parser("type", help="type the documents by hand, timed")
    r = sub.add_parser("report", help="medians, ratio and wrong values approved")
    r.add_argument("--name", default="pilot")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        return prepare(args.force)
    if args.command == "type":
        return type_by_hand()
    return report(args.name)


if __name__ == "__main__":
    raise SystemExit(main())
