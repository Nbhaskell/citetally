"""The personal-information guard: what it flags, what it allows, and what it never prints."""

import pytest

from tools.check_personal_info import (
    Finding,
    check_author,
    is_excluded,
    main,
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
def test_flags_notes_about_the_owner(text: str) -> None:
    assert labels(text) == ["note about the owner"]


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
