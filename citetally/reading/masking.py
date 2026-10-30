"""Hide card numbers and labelled bank account numbers before a model sees the text.

A card number is a run of 13 to 19 digits that passes the Luhn check, has a card network's length
and starting digits, and is not part of a longer reference or an amount. Only the last four
digits are kept. This is code, not a model's judgement, and it runs on the stored words as well as
on text. Account, routing, ABA and IBAN numbers are masked only when a label says what they are,
and only in text sent to a model. Page images cannot be masked this way (docs/TRD.md section 11).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from citetally.models import Word
from citetally.reading import layout

MASK = "*"
KEEP = 4  # digits left visible at the end
_MIN_DIGITS = 13
_MAX_DIGITS = 19
_MAX_GAP_CHARS = 3.0  # words further apart than this many letters are in different columns

# (starting digits, lengths): the major card networks.
_NETWORKS: tuple[tuple[tuple[str, ...], tuple[int, ...]], ...] = (
    (("4",), (13, 16, 19)),  # Visa
    (("51", "52", "53", "54", "55"), (16,)),  # Mastercard
    (tuple(str(n) for n in range(2221, 2721)), (16,)),  # Mastercard, 2-series
    (("34", "37"), (15,)),  # American Express
    (("6011", "65", "644", "645", "646", "647", "648", "649"), (16, 17, 18, 19)),  # Discover
    (("300", "301", "302", "303", "304", "305", "36", "38", "39"), (14, 15, 16, 17, 18, 19)),
    (tuple(str(n) for n in range(3528, 3590)), (16, 17, 18, 19)),  # JCB
    (("62",), (16, 17, 18, 19)),  # UnionPay
)

# A digit run in text: groups of digits joined by single spaces or hyphens, standing alone.
_DIGIT_RUN = re.compile(r"(?<![\w.,$/-])\d+(?:[ -]\d+)*(?![\w/]|[.,]\d)")
_NUMERIC_WORD = re.compile(r"-?\d+(?:-\d+)*-?")

_LABEL = (
    r"(?:(?:bank\s+)?(?:account|acct|a/c)\s*(?:number|num|no|nr|#)\.?"
    r"|routing(?:\s*(?:number|num|no|#))?\.?"
    r"|\baba(?:\s*(?:number|no|#))?\.?)"
)
_SEPARATOR = r"[ \t:#.]*"
_LABELLED_DIGITS = re.compile(
    rf"(?P<label>{_LABEL}){_SEPARATOR}(?P<value>\d+(?:[ -]\d+)*)(?![\w])", re.IGNORECASE
)
_LABELLED_IBAN = re.compile(
    rf"(?P<label>\biban\b){_SEPARATOR}(?P<value>[A-Z]{{2}}\d{{2}}(?: ?[A-Z0-9]{{1,4}})+)(?![\w])",
    re.IGNORECASE,
)


def luhn_valid(digits: str) -> bool:
    """The Luhn check on a string of digits and nothing else."""
    if not digits or not digits.isascii() or not digits.isdigit():
        return False
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def is_card_number(digits: str) -> bool:
    """Digits that pass the Luhn check and have a card network's starting digits and length."""
    if not _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
        return False
    on_network = any(
        len(digits) in lengths and digits.startswith(prefixes) for prefixes, lengths in _NETWORKS
    )
    return on_network and luhn_valid(digits)


def _card_windows(groups: Sequence[str]) -> list[tuple[int, int]]:
    """Spans (first, last group, inclusive) whose digits joined make a card number.

    From each starting group the longest span that is a card wins, and the next search begins
    after it. A span may start early, so a stray group before a card can be masked along with it,
    but the card is never left showing.
    """
    found: list[tuple[int, int]] = []
    start = 0
    while start < len(groups):
        best = -1
        digits = ""
        for end in range(start, len(groups)):
            digits += groups[end]
            if len(digits) > _MAX_DIGITS:
                break
            if is_card_number(digits):
                best = end
        if best >= 0:
            found.append((start, best))
            start = best + 1
        else:
            start += 1
    return found


def _mask_digits(pieces: Sequence[str], keep: int = KEEP) -> list[str]:
    """Replace every digit with a mask character except the last `keep` digits overall."""
    remaining = sum(ch.isdigit() for piece in pieces for ch in piece) - keep
    out: list[str] = []
    for piece in pieces:
        chars = []
        for ch in piece:
            if ch.isdigit():
                chars.append(MASK if remaining > 0 else ch)
                remaining -= 1
            else:
                chars.append(ch)
        out.append("".join(chars))
    return out


def mask_card_numbers(text: str) -> str:
    """Text with every card-like number masked except its last four digits."""

    def replace(match: re.Match[str]) -> str:
        run = match.group(0)
        parts = re.split(r"([ -])", run)  # digit groups and the separators between them
        groups = parts[::2]
        spans = _card_windows(groups)
        for first, last in spans:
            pieces = parts[2 * first : 2 * last + 1]
            parts[2 * first : 2 * last + 1] = _mask_digits(pieces)
        return "".join(parts)

    return _DIGIT_RUN.sub(replace, text)


def _same_column_run(previous: Word, current: Word) -> bool:
    """Whether two words on one line are close enough to belong to one number."""
    letters = max(len(previous.t), 1)
    char_width = (previous.x1 - previous.x0) / letters
    return current.x0 - previous.x1 <= _MAX_GAP_CHARS * char_width


def mask_words(words: Sequence[Word]) -> list[Word]:
    """The same words, in the same order, with card-like numbers masked in their text.

    Digits that OCR split into several words on one line are joined for the check, so a card
    number cannot get past by being read in pieces. Boxes and confidences are untouched.
    """
    result = list(words)
    for line in layout.line_indices(words):
        run: list[int] = []
        runs: list[list[int]] = []
        for index in line:
            numeric = _NUMERIC_WORD.fullmatch(words[index].t) is not None
            if numeric and (not run or _same_column_run(words[run[-1]], words[index])):
                run.append(index)
                continue
            if run:
                runs.append(run)
            run = [index] if numeric else []
        if run:
            runs.append(run)
        for members in runs:
            groups = [re.sub(r"\D", "", words[i].t) for i in members]
            for first, last in _card_windows(groups):
                chosen = members[first : last + 1]
                masked = _mask_digits([words[i].t for i in chosen])
                for i, text in zip(chosen, masked, strict=True):
                    result[i] = words[i].model_copy(update={"t": text})
    return result


def _mask_alphanumerics(value: str, keep: int = KEEP) -> str:
    remaining = sum(ch.isalnum() for ch in value) - keep
    chars = []
    for ch in value:
        if ch.isalnum():
            chars.append(MASK if remaining > 0 else ch)
            remaining -= 1
        else:
            chars.append(ch)
    return "".join(chars)


def mask_labelled_numbers(text: str) -> str:
    """Text with account, routing, ABA and IBAN numbers masked when a label names them."""

    def digits(match: re.Match[str]) -> str:
        value = match.group("value")
        if sum(ch.isdigit() for ch in value) < 6:
            return match.group(0)
        start = match.start("value") - match.start()
        return match.group(0)[:start] + _mask_alphanumerics(value)

    def iban(match: re.Match[str]) -> str:
        start = match.start("value") - match.start()
        return match.group(0)[:start] + _mask_alphanumerics(match.group("value"))

    return _LABELLED_IBAN.sub(iban, _LABELLED_DIGITS.sub(digits, text))


def mask_for_model(text: str) -> str:
    """Everything that must not reach a model: card numbers and labelled account numbers."""
    return mask_labelled_numbers(mask_card_numbers(text))
