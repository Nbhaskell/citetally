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
_FIGURES = r"(?:totals?|figures?|amounts?|balances?|line items?|numbers?)"
_BEFORE = r"(?:above|before|earlier|previous|preceding|prior)"
# The step that would catch a document, and the words that may stand between a verb and it.
_QUALIFIERS = (
    r"(?:(?:the|a|an|all|any|every|each|further|usual|normal|regular|standard|routine|this|these"
    r"|those|our|your|its|their|manual|second|extra|additional|vendor|supplier|duplicate|date"
    r"|payment|approval|verification)\s+){0,4}"
)
_PROCESS_STEP = (
    r"(?:checks?|reviews?|approvals?|queue|verifications?|validations?|audits?|sign-?offs?|look"
    r"|step|scrutiny|controls?)"
)
_PROCESS_NOUN = (
    r"(?:checks?|reviews?|reviewers?|approvals?|approvers?|queue|verifications?|validations?"
    r"|audits?|sign-?offs?|discrepanc\w+|duplicates?|scrutiny)"
)
PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\b"
        + _GAP
        + r"\b(?:instructions?|rules?|prompts?|directions?|guidelines?|checks?)\b"
        # telling the reader to set aside what is printed earlier on the page
        + r"|\b(?:ignore|disregard|forget)\b"
        + _GAP
        + rf"\b(?:{_BEFORE}\s+{_FIGURES}|(?:{_FIGURES}|everything|anything)\b{_GAP}\b{_BEFORE})\b"
    ),
    "role_change": re.compile(
        r"\byou are (?:now |no longer )?(?:an? |the )?"
        r"(?:ai|assistant|language model|llm|chatbot|bot)\b"
        r"|\bact as (?:an? |the )?(?:ai|assistant|auditor|approver|reviewer)\b"
        r"|\bpretend (?:to be|you are)\b"
    ),
    "addresses_assistant": re.compile(
        r"\b(?:dear|attention|note to|note for|message for|message to|instructions? for|hey)\s+"
        r"(?:the\s+)?(?:ai(?: systems?| assistants?)?|assistant|model|llm|bot|chatbot|approver"
        r"|auditor|reviewer|automated (?:system|reviewer|tool))\b"
        r"|\bto whoever is (?:processing|reviewing|handling|reading|approving)\b"
    ),
    "approval_directive": re.compile(
        r"\bapprove (?:this|it|the) (?:invoice|payment|entry|document|expense|receipt)\b"
        r"|\bapprove (?:it |them |these )?(?:automatically|immediately|at once|straight away"
        r"|right away)\b"
        r"|\bthis (?:vendor|supplier|invoice|payment|document|account|entry) "
        r"(?:(?:is|was) (?:already |pre-?)|has already been (?:pre-?)?)"
        r"(?:approved|authori[sz]ed|cleared|verified)\b"
        r"|\bmark(?: (?:this|it|the \w+))? as (?:approved|paid|reviewed|verified|valid|checked"
        r"|reconciled|cleared)\b"
        r"|\b(?:do not|don't|never) (?:flag|check|review|verify|question|dispute|audit)\b"
        r"|\bskip (?:(?:the|all|any|every|further|these|this|those) )*"
        r"(?:checks?|review|verification|validation)\b"
        r"|\bwithout (?:any )?(?:review|checking|verification)\b"
    ),
    "system_markers": re.compile(
        r"<\s*/?\s*(?:system|assistant|instructions?|prompt)\b|\[/?(?:inst|system)\]"
        r"|\bsystem (?:message|notice|override|instruction)s?\s*:"
        r"|\bsystem prompt\b|\bbegin (?:system|instructions?)\b|#{2,}\s*(?:system|instructions?)\b"
        # a label that presents the line as coming from a machine or a hidden channel
        r"|\[\s*(?:automated|system|ai)\s+(?:note|message|notice)\s*\]"
        r"|\b(?:hidden|secret|embedded|invisible)\s+(?:instruction|note|message|command|directive)s?\b"
    ),
    # Telling the reader to leave out the step that would catch the document: skipping, bypassing
    # or holding back a check, a review or an approval, or doing without one.
    "skip_review": re.compile(
        rf"\b(?:skip|bypass|suspend|waive|omit|disable|circumvent)s?\s+{_QUALIFIERS}{_PROCESS_STEP}\b"
        rf"|\b(?:do not|don't|never|no need to|not to)\b(?: \w+){{0,3}}? "
        rf"(?:hold|apply|run|perform|wait|mention|report|disclose|raise|escalate|delay)\b"
        rf"{_GAP}\b{_PROCESS_NOUN}\b"
        rf"|\bwithout (?:asking|any|further|more|waiting|requiring|raising|needing)\b"
        rf"{_GAP}\b(?:questions?|approval|review|checks?|verification|confirmation|sign-?off)\b"
        rf"|\bno (?:further |more |additional |extra )?(?:checks?|reviews?|approvals?|sign-?offs?"
        rf"|verification|validation)(?: (?:is|are))? (?:needed|required|necessary|applies|apply)\b"
    ),
    # Asking for figures to be taken on trust, or for the document to be passed on unexamined.
    "accept_as_verified": re.compile(
        r"\b(?:treat|accept|take|regard|consider|handle)\b" + _GAP + r"\bas (?:verified|audited|"
        r"checked|cleared|correct|authori[sz]ed|printed|pre-?approved)\b"
        r"|\b(?:release|post|send|push|export|forward)\b" + _GAP + r"\b(?:straight|directly) "
        r"(?:to|into) (?:the )?(?:ledger|books)\b"
    ),
    # Asking for a value to be replaced or left out.
    "value_control": re.compile(
        r"\b(?:record|set|change|replace|overwrite|substitute)\b" + _GAP + r"\b(?:the )?(?:vendor "
        r"name|vendor|payee|supplier|total|balance|amount due)\b" + _GAP + r"\b(?:as|to|with)\b"
        r"|\bleave\b" + _GAP + r"\b(?:the )?(?:vendor(?: name)?|payee|total|balance|amount due"
        r"|invoice number)\b" + _GAP + r"\b(?:blank|empty|unset)\b"
    ),
    # Handing the reader a different job, or asking it to hand over what it holds.
    "new_task": re.compile(
        r"\b(?:your|the) (?:new|real|actual|true) (?:task|job|goal|purpose|mission|assignment)\b"
        r"|\bfrom now on\b" + _GAP + r"\b(?:respond|reply|answer|you|always|only|ignore)\b"
        r"|\b(?:list|reveal|disclose|leak|send)\b"
        + _GAP
        + r"\b(?:every|all)\b"
        + _GAP
        + r"\b(?:on file|in your (?:records|database|system|memory)|you (?:know|have))\b"
        r"|\b(?:report|label|describe|present)\b" + _GAP + r"\bas (?:clean|valid|fine|having no)\b"
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
