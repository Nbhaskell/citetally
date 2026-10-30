"""Print counts for the golden set: by split, condition, family and planted problem.

  python -m tools.synthetic.report

Reads only the small summary file next to the golden file (its header), so reading the report never
means opening a held-out document or its truth.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from tools.synthetic.golden import GOLDEN_FILE, summary_path


def _table(title: str, counts: dict[str, int]) -> list[str]:
    width = max((len(k) for k in counts), default=0)
    return ["", title, *(f"  {key:<{width}}  {value:>4}" for key, value in counts.items())]


def render(header: dict[str, Any]) -> str:
    counts = header["counts"]
    lines = [
        f"Golden set v{header['version']}  seed {header['seed']}  {header['generator']}",
        f"{counts['documents']} documents, "
        f"{counts['with_planted_problem']} with one planted problem",
    ]
    lines += _table("By split", counts["by_split"])
    lines += _table("Planted problems by split", counts["planted_by_split"])
    lines += _table("By condition and split", counts["by_split_and_condition"])
    lines += _table("By planted kind", counts["by_planted_kind"])
    lines += _table("By template family", counts["by_family"])
    families = counts["families_by_split"]
    lines += [
        "",
        f"Tuned families ({len(families['tuned'])}): {', '.join(families['tuned'])}",
        f"Held-out families ({len(families['heldout'])}): {', '.join(families['heldout'])}",
        "Held-out documents are sealed until Phase 8.",
    ]
    return "\n".join(lines)


def main(path: Path | None = None) -> int:
    header = json.loads((path or summary_path(GOLDEN_FILE)).read_text(encoding="utf-8"))
    print(render(header))
    return 0


if __name__ == "__main__":
    sys.exit(main())
