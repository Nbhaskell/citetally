"""Instruction-like text in a document (SUSPICIOUS_TEXT; CLAUDE.md rule 7).

A page can say anything. Text aimed at an assistant or an approver is not obeyed (the extraction
prompt declares page text to be data, and approval needs a person), but it is flagged so the
reviewer knows someone tried. Matching is done on a normalised copy of the text, so case,
full-width letters, accents, invisible characters, look-alike letters from other
alphabets and line breaks inside a phrase do not hide it. Results name the pattern and the page,
never the matched text.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

# Letters from other alphabets that look like Latin ones, as a document author might use them.
_LOOKALIKES = str.maketrans(
    {
        0x0430: "a",
        0x0435: "e",
        0x043E: "o",
        0x0440: "p",
        0x0441: "c",
        0x0445: "x",
        0x0443: "y",
        0x0456: "i",
        0x0458: "j",
        0x0455: "s",
        0x0501: "d",
        0x04BB: "h",
        0x0578: "n",
        0x03B1: "a",
        0x03BF: "o",
        0x03B9: "i",
        0x03BD: "v",
        0x03C1: "p",
        0x03C4: "t",
        0x03C5: "u",
        0x03B5: "e",
        0x03BA: "k",
    }
)  # code points: Cyrillic, Greek and Armenian letters
_INVISIBLE = {"Cf", "Cc", "Mn"}  # format controls, control characters, combining marks

_GAP = r"[^.\n]{0,40}?"
PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\b"
        + _GAP
        + r"\b(?:instructions?|rules?|prompts?|directions?|guidelines?|checks?)\b"
    ),
    "role_change": re.compile(
        r"\byou are (?:now |no longer )?(?:an? |the )?"
        r"(?:ai|assistant|language model|llm|chatbot|bot)\b"
        r"|\bact as (?:an? |the )?(?:ai|assistant|auditor|approver|reviewer)\b"
        r"|\bpretend (?:to be|you are)\b"
    ),
    "addresses_assistant": re.compile(
        r"\b(?:dear|attention|note to|message for|instructions? for|hey)\s+(?:the\s+)?"
        r"(?:ai|assistant|model|llm|bot|chatbot|approver|auditor|automated (?:system|reviewer))\b"
    ),
    "approval_directive": re.compile(
        r"\bapprove (?:this|it|the) (?:invoice|payment|entry|document|expense|receipt)\b"
        r"|\bmark (?:this|it|the \w+) as (?:approved|paid|reviewed|verified|valid|checked)\b"
        r"|\b(?:do not|don't|never) (?:flag|check|review|verify|question|dispute|audit)\b"
        r"|\bskip (?:the )?(?:checks?|review|verification|validation)\b"
        r"|\bwithout (?:any )?(?:review|checking|verification)\b"
    ),
    "system_markers": re.compile(
        r"<\s*/?\s*(?:system|assistant|instructions?|prompt)\b|\[/?(?:inst|system)\]"
        r"|\bsystem prompt\b|\bbegin (?:system|instructions?)\b|#{2,}\s*(?:system|instructions?)\b"
    ),
    "asks_for_output": re.compile(
        r"\b(?:reveal|print|show|repeat|output)\b"
        + _GAP
        + r"\b(?:system prompt|your instructions|your prompt)\b"
        r"|\b(?:respond|reply|answer) (?:only )?with\b" + _GAP + r"\b(?:json|approved|ok|yes)\b"
        r"|\bset (?:the )?(?:total|amount|balance|vendor)\b" + _GAP + r"\bto\b"
    ),
}


@dataclass(frozen=True)
class Finding:
    pattern: str  # a key of PATTERNS, or "extra_phrase"
    page_number: int


def normalise(text: str) -> str:
    """The text a pattern is matched against: no case, width, invisible or look-alike tricks."""
    folded = unicodedata.normalize("NFKD", text)
    kept = "".join(
        ch for ch in folded if ch.isspace() or unicodedata.category(ch) not in _INVISIBLE
    )
    straight = (
        kept.translate(_LOOKALIKES).replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").casefold()
    )
    return " ".join(straight.split())


def scan(pages: Sequence[str], extra_phrases: Sequence[str] = ()) -> list[Finding]:
    """Every pattern that matches on each page (page numbers start at 1)."""
    phrases = [(phrase, normalise(phrase)) for phrase in extra_phrases]
    findings = []
    for number, text in enumerate(pages, start=1):
        clean = normalise(text)
        for name, pattern in PATTERNS.items():
            if pattern.search(clean):
                findings.append(Finding(name, number))
        for _, phrase in phrases:
            if phrase and phrase in clean:
                findings.append(Finding("extra_phrase", number))
    return findings
