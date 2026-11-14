"""The personal-information guard: what it flags, what it allows, and what it never prints."""

from pathlib import Path

import pytest

from tools.check_personal_info import (
    Finding,
    check_author,
    is_excluded,
    main,
    scan_message,
    scan_text,
)

# Built from parts so this file never contains a real-looking address or path itself.
WINDOWS_HOME = "C:" + "\\Users\\" + "jdoe" + "\\project"
POSIX_HOME = "/home/" + "jdoe" + "/project"
MAC_HOME = "/Users/" + "jdoe" + "/project"
PERSONAL_EMAIL = "jdoe" + "@" + "gmail.com"
PHONE = "(212) " + "867-5309"


def labels(text: str, path: str = "docs/notes.md") -> list[str]:
    return [f.label for f in scan_text(path, text)]


@pytest.mark.parametrize("home", [WINDOWS_HOME, POSIX_HOME, MAC_HOME])
def test_flags_local_user_paths(home: str) -> None:
    assert labels(f"run it from {home}") == ["local user path"]


@pytest.mark.parametrize(
    "text",
    [
        r"C:\Users\Public\Documents",
        "/home/runner/work/repo",
        r"C:\Users\<you>\citetally",
        "/Users/<name>/citetally",
    ],
)
def test_allows_generic_paths_and_placeholders(text: str) -> None:
    assert labels(text) == []


def test_flags_a_personal_email_address() -> None:
    assert labels(f"contact {PERSONAL_EMAIL}") == ["email address"]


@pytest.mark.parametrize(
    "address",
    [
        "billing@example.com",
        "16366851+someone@users.noreply.github.com",
        "noreply@github.com",
        "ap@vendor.example.org",
    ],
)
def test_allows_invented_and_noreply_addresses(address: str) -> None:
    assert labels(f"mail {address}") == []


def test_flags_a_real_looking_phone_number_but_not_555_01xx() -> None:
    assert labels(f"call {PHONE}") == ["phone number"]
    assert labels("call 555-0142 or (212) 555-0188") == []


@pytest.mark.parametrize(
    "text",
    [
        "The owner is new to the terminal.",
        "Not a professional developer, explain gently.",
        "Keep costs low: cost-worried about API spend.",
        "My budget is small.",
        "Written for a beginner.",
    ],
)
def test_flags_notes_about_the_author(text: str) -> None:
    assert "note about the author" in labels(text)


def test_instructions_written_without_describing_the_person_pass() -> None:
    assert labels("Explain steps in plain language. Use only free, local tools.") == []


def test_assistant_instruction_files_are_flagged_by_path() -> None:
    assert labels("anything", path="CLAUDE.md") == ["assistant-instruction file"]
    assert labels("anything", path="CLAUDE.local.md") == ["assistant-instruction file"]
    assert labels("anything", path="docs/CLAUDE.md") == ["assistant-instruction file"]


def test_findings_carry_line_numbers_and_never_the_matched_text() -> None:
    findings = scan_text("README.md", f"fine\nmail {PERSONAL_EMAIL}\nfine")
    assert findings == [Finding("README.md", 2, "email address")]
    assert PERSONAL_EMAIL not in repr(findings)


def test_lock_files_generated_files_and_the_checker_itself_are_skipped() -> None:
    for path in (
        "web/package-lock.json",
        "requirements.lock",
        "web/src/api/schema.d.ts",
        "tools/check_personal_info.py",
        "tests/test_check_personal_info.py",
    ):
        assert is_excluded(path), path
    assert not is_excluded("README.md")


@pytest.mark.parametrize(
    "email",
    ["16366851+someone@users.noreply.github.com", "someone@users.noreply.github.com"],
)
def test_noreply_commit_email_is_accepted(email: str) -> None:
    assert check_author(email) is None


@pytest.mark.parametrize("email", [PERSONAL_EMAIL, "", "me@" + "work.example"])
def test_any_other_commit_email_is_refused(email: str) -> None:
    message = check_author(email)
    assert message is not None
    assert PERSONAL_EMAIL not in message


def test_main_reports_findings_without_text_and_exits_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = {"README.md": f"mail {PERSONAL_EMAIL}\n", "ok.md": "nothing here\n"}
    code = main(["--staged"], read_files=lambda: files, author_email="a@users.noreply.github.com")
    out = capsys.readouterr().out
    assert code == 1
    assert "README.md:1: email address" in out
    assert PERSONAL_EMAIL not in out


def test_main_exits_zero_when_clean(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["--staged"],
        read_files=lambda: {"ok.md": "nothing here\n"},
        author_email="a@users.noreply.github.com",
    )
    assert code == 0
    assert "No personal information found" in capsys.readouterr().out


def test_main_blocks_a_personal_commit_email_in_staged_mode_only() -> None:
    clean = {"ok.md": "nothing here\n"}
    assert main(["--staged"], read_files=lambda: clean, author_email=PERSONAL_EMAIL) == 1
    # CI checks files, not who is committing.
    assert main(["--all"], read_files=lambda: clean, author_email=PERSONAL_EMAIL) == 0


# --- wording about a person, in Markdown and commit messages ------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The owner accepted the tool.",
        "Confirmed by the owner on 3 Nov.",
        "That is the owner's decision.",
        "I measured the run and it took 30 seconds.",
        "As far as I know the wheel is LGPL.",
        "I do not know why the gap exists.",
        "Compared in my check against the key.",
        "We decided to leave it out.",
    ],
)
def test_wording_about_a_person_is_flagged_in_markdown(text: str) -> None:
    found = labels(text, "docs/NOTES.md")
    assert found and all("describe the" in label for label in found)


@pytest.mark.parametrize(
    "text",
    [
        "The tool was accepted.",
        "Owner-operator (primary buyer): less retyping.",
        "A bookkeeper or owner clearing a pile of invoices.",
        "1. As a bookkeeper, I drag in a folder of PDFs and see them processed.",
        "- As an owner, I am warned when the same invoice shows up twice.",
        "A capital I and a lower-case l look the same.",
        "Part I of the plan; the I/O layer.",
        "Measured at 30 seconds per page.",
    ],
)
def test_neutral_wording_and_product_roles_are_allowed(text: str) -> None:
    assert labels(text, "docs/NOTES.md") == []


def test_the_wording_rule_applies_to_markdown_only() -> None:
    assert labels("I measured it; the owner decided.", "tools/notes.py") == []
    assert labels("I measured it; the owner decided.", "README.md") != []


def test_a_commit_message_is_checked_for_attribution_and_wording() -> None:
    assert scan_message("Add the currency rule (D-085)\n\nThe page's currency is used.") == []
    bad = scan_message(
        "Fix it\n\nCo-Authored-By: someone\nGenerated with a tool\nI think this is right."
    )
    assert [f.label for f in bad] == [
        "assistant attribution line",
        "assistant attribution line",
        "first person (describe the action)",
    ]
    assert scan_message("# a comment line from git\nTax rule") == []


def test_main_checks_a_message_file(tmp_path: Path) -> None:
    clean = tmp_path / "ok.txt"
    clean.write_text("Add the rule\n", encoding="utf-8")
    dirty = tmp_path / "bad.txt"
    dirty.write_text("Add the rule\n\nCo-Authored-By: someone\n", encoding="utf-8")
    assert main(["--message", str(clean)]) == 0
    assert main(["--message", str(dirty)]) == 1


# --- wording findings warn; personal information blocks ------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "| 1 | Type: `I need the March invoices.` | The queue shows three entries. |",
        "I need the report by Friday.",
        "I feed the cat; I speed up; I heed it; I seed the data.",
        "I proceed; I succeed; I exceed the limit.",
    ],
)
def test_words_that_end_in_ed_but_are_not_past_tense_are_not_first_person(text: str) -> None:
    assert labels(text, "docs/NOTES.md") == []
    assert scan_message(text) == []


@pytest.mark.parametrize(
    "verb",
    ["needed", "feeded", "speeded", "heeded", "seeded", "proceeded", "succeeded", "exceeded"],
)
def test_a_past_tense_verb_after_i_is_still_found(verb: str) -> None:
    assert labels(f"I {verb} more data.", "docs/NOTES.md") != []


def test_wording_findings_are_warnings_and_personal_information_is_not() -> None:
    found = scan_text(
        "docs/NOTES.md", f"I measured it.\nThe owner decided.\nmail {PERSONAL_EMAIL}\n"
    )
    assert [(f.line, f.warning) for f in found] == [(1, True), (2, True), (3, False)]
    assert [f.warning for f in scan_text("docs/NOTES.md", "A beginner wrote this.")] == [False]


def test_commit_message_wording_is_a_warning_and_attribution_is_not() -> None:
    found = scan_message("Fix it\n\nCo-Authored-By: someone\nI think so.\nThe owner agreed.")
    assert [(f.line, f.warning) for f in found] == [(3, False), (4, True), (5, True)]


def test_main_prints_wording_warnings_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    files = {"docs/NOTES.md": "I measured the run.\n"}
    code = main(["--staged"], read_files=lambda: files, author_email="a@users.noreply.github.com")
    out = capsys.readouterr().out
    assert code == 0
    assert "Doc wording warnings" in out
    assert "docs/NOTES.md:1: first person" in out
    assert "Personal information check failed" not in out
    assert "No personal information found in 1 files." in out


def test_main_blocks_on_personal_information_and_still_prints_the_warnings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = {"docs/NOTES.md": f"I measured the run.\nmail {PERSONAL_EMAIL}\n"}
    code = main(["--all"], read_files=lambda: files)
    out = capsys.readouterr().out
    assert code == 1
    assert "docs/NOTES.md:1: first person" in out.split("Personal information check failed")[0]
    assert "docs/NOTES.md:2: email address" in out.split("Personal information check failed")[1]


def test_a_commit_message_with_wording_only_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wording = tmp_path / "wording.txt"
    wording.write_text("Add the rule\n\nI think this is right.\n", encoding="utf-8")
    assert main(["--message", str(wording)]) == 0
    out = capsys.readouterr().out
    assert "Doc wording warnings" in out
    assert "line 3: first person" in out
    assert "Commit message check failed" not in out
    note = tmp_path / "note.txt"
    note.write_text("Add the rule\n\nWritten by a beginner.\n", encoding="utf-8")
    assert main(["--message", str(note)]) == 1
