"""The statistics the report leans on, in plain code with no dependencies.

Three things matter for an honest comparison on a few hundred documents:
- a proportion is reported with its uncertainty (Wilson interval), not alone;
- a change between two settings is compared with how much the same setting varies from one pass
  to the next (t-interval across passes);
- the documents are the sample, so the change is also bootstrapped over documents, paired (the same
  document under both settings).
A difference is called real only when both hold. Meeting only one is "unclear".
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

# Two-sided 95% critical values of Student's t for 1 to 10 degrees of freedom; beyond that, 1.96.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
}  # fmt: skip
_Z95 = 1.959964


def wilson(successes: int, total: int, z: float = _Z95) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion; None when there is nothing to measure."""
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def t_halfwidth(values: Sequence[float]) -> float | None:
    """Half-width of the 95% t-interval of the mean of per-pass values; None below 2 passes."""
    n = len(values)
    if n < 2:
        return None
    critical = _T95.get(n - 1, _Z95)
    return critical * statistics.stdev(values) / math.sqrt(n)


@dataclass(frozen=True)
class Bootstrap:
    mean: float
    low: float
    high: float

    @property
    def excludes_zero(self) -> bool:
        return self.low > 0 or self.high < 0


def paired_bootstrap(
    differences: Sequence[float], *, rounds: int = 10_000, seed: int = 20261101
) -> Bootstrap | None:
    """Mean of per-document differences with a 95% percentile interval from resampling documents."""
    n = len(differences)
    if n == 0:
        return None
    rng = random.Random(seed)
    means = sorted(sum(differences[rng.randrange(n)] for _ in range(n)) / n for _ in range(rounds))
    return Bootstrap(
        mean=sum(differences) / n,
        low=means[int(0.025 * rounds)],
        high=means[int(0.975 * rounds) - 1],
    )


@dataclass(frozen=True)
class Comparison:
    verdict: str  # "real", "unclear" or "no difference found"
    difference: float
    bootstrap: Bootstrap | None
    pass_spread: float | None  # half-width of the t-interval across passes, for the setting pair
    beats_spread: bool | None
    detectable: float | None  # the smallest difference the test could have called real


def compare(pass_differences: Sequence[float], document_differences: Sequence[float]) -> Comparison:
    """`pass_differences`: setting B minus setting A, one number per pass (same pass index).
    `document_differences`: B minus A per document, averaged over passes."""
    boot = paired_bootstrap(document_differences)
    difference = (
        sum(pass_differences) / len(pass_differences)
        if pass_differences
        else (boot.mean if boot else 0.0)
    )
    spread = t_halfwidth(pass_differences)
    beats = None if spread is None else abs(difference) > spread
    by_boot = bool(boot and boot.excludes_zero)
    if spread is None:
        # One pass per setting: the pass-to-pass condition cannot be checked, so it cannot be met.
        verdict = "unclear" if by_boot else "no difference found"
    elif by_boot and beats:
        verdict = "real"
    elif by_boot or beats:
        verdict = "unclear"
    else:
        verdict = "no difference found"
    detectable = None if boot is None else (boot.high - boot.low) / 2
    return Comparison(verdict, difference, boot, spread, beats, detectable)
