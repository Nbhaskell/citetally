"""Block personal information from being committed.

  python tools/check_personal_info.py --staged   what the git pre-commit hook runs
  python tools/check_personal_info.py --all      every tracked file (CI runs this)

Flags local user-profile paths, email addresses and phone numbers that are not invented ones,
notes that describe the owner (experience, budget), assistant-instruction files, and (with
--staged) a commit email that is not a GitHub noreply address. Findings print the file, the
line and a label, never the matched text, so CI logs do not repeat what was found.

Standard library only. Turn the hook on once per clone: git config core.hooksPath .githooks
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# User-profile folders. Placeholders such as <you> or {id} do not start with a letter or digit,
# so they never match. The names below are generic folders, not people.
_GENERIC_NAMES = {"public", "default", "user", "username", "you", "name", "runner", "example"}
_LOCAL_PATH = re.compile(
    r"(?:(?i:[a-z]:[\\/]+users[\\/]+)|(?<![\w.])/Users/|(?<![\w.])/home/)([A-Za-z0-9][\w.-]*)"
)
_EMAIL = re.compile(r"[\w.+-]+@((?:[\w-]+\.)+[A-Za-z]{2,})")
_PHONE = re.compile(r"(?<!\d)(?:\(\d{3}\)\s?|\d{3}[-. ])(\d{3})[-. ](\d{4})(?!\d)")
_OWNER_NOTE = re.compile(
    r"\bnew to (?:the )?(?:terminal|command line|coding|programming|python|git)\b"
    r"|\bnot a (?:professional )?(?:developer|programmer|engineer)\b"
    r"|\bcost-worried\b|\bbeginner\b|\bnovice\b"
    r"|\bmy (?:budget|salary|income|experience level)\b"
    r"|\bno (?:paid )?api account\b",
    re.IGNORECASE,
)

_FAKE_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
_NOREPLY_DOMAIN = "users.noreply.github.com"
_ASSISTANT_FILES = {"claude.md", "claude.local.md"}
_EXCLUDED_SUFFIXES = (
    "package-lock.json",
    ".lock",
    "schema.d.ts",
    "tools/check_personal_info.py",
    "tests/test_check_personal_info.py",
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    label: str


def is_excluded(path: str) -> bool:
    """Generated files, lock files and this checker (whose patterns look like what it flags)."""
    return path.replace("\\", "/").endswith(_EXCLUDED_SUFFIXES)


def _email_is_invented(domain: str, local: str) -> bool:
    domain = domain.lower()
    if domain == "github.com" and local.lower() == "noreply":
        return True
    if domain == _NOREPLY_DOMAIN or domain.endswith("." + _NOREPLY_DOMAIN):
        return True
    return any(domain == d or domain.endswith("." + d) for d in _FAKE_EMAIL_DOMAINS)


def scan_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    if PurePosixPath(path.replace("\\", "/")).name.lower() in _ASSISTANT_FILES:
        findings.append(Finding(path, 1, "assistant-instruction file"))
    for number, line in enumerate(text.splitlines(), start=1):
        labels: list[str] = []
        if any(m.group(1).lower() not in _GENERIC_NAMES for m in _LOCAL_PATH.finditer(line)):
            labels.append("local user path")
        for match in _EMAIL.finditer(line):
            local = match.group(0).split("@", 1)[0]
            if not _email_is_invented(match.group(1), local):
                labels.append("email address")
                break
        for match in _PHONE.finditer(line):
            if not (match.group(1) == "555" and match.group(2).startswith("01")):
                labels.append("phone number")
                break
        if _OWNER_NOTE.search(line):
            labels.append("note about the owner")
        findings.extend(Finding(path, number, label) for label in labels)
    return findings


def check_author(email: str) -> str | None:
    """None if commits would carry a GitHub noreply address, else what to do about it."""
    if email.lower().endswith("@" + _NOREPLY_DOMAIN):
        return None
    return (
        "The commit email is not a GitHub noreply address, so it would be published with the "
        "commit. Set it with: git config user.email <id>+<username>@users.noreply.github.com"
    )


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def _decode(data: bytes) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None  # binary file


def _staged_files() -> dict[str, str]:
    names = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split(b"\0")
    files: dict[str, str] = {}
    for raw in filter(None, names):
        name = raw.decode("utf-8")
        text = _decode(_git("show", f":{name}"))
        if text is not None:
            files[name] = text
    return files


def _tracked_files() -> dict[str, str]:
    files: dict[str, str] = {}
    for raw in filter(None, _git("ls-files", "-z").split(b"\0")):
        name = raw.decode("utf-8")
        try:
            text = _decode(Path(name).read_bytes())
        except OSError:
            continue
        if text is not None:
            files[name] = text
    return files


def _author_email() -> str:
    ident = _git("var", "GIT_AUTHOR_IDENT").decode("utf-8")
    match = re.search(r"<([^>]*)>", ident)
    return match.group(1) if match else ""


def main(
    argv: Sequence[str] | None = None,
    read_files: Callable[[], Mapping[str, str]] | None = None,
    author_email: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Block personal information from commits.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="check files staged for commit")
    mode.add_argument("--all", action="store_true", help="check every tracked file")
    args = parser.parse_args(argv)

    files = (read_files or (_staged_files if args.staged else _tracked_files))()
    problems: list[str] = []
    scanned = 0
    for path, text in sorted(files.items()):
        if is_excluded(path):
            continue
        scanned += 1
        problems += [f"{f.path}:{f.line}: {f.label}" for f in scan_text(path, text)]
    if args.staged:
        message = check_author(_author_email() if author_email is None else author_email)
        if message:
            problems.append(message)

    if problems:
        print("Personal information check failed:")
        print("\n".join(f"  {p}" for p in problems))
        print("The matched text is not shown. Remove it or replace it with an invented value.")
        return 1
    print(f"No personal information found in {scanned} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
