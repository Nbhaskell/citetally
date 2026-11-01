"""CLAUDE.md rule 1: nothing is paid, posted or sent. The only way out is a downloaded CSV.

This reads the source and fails if any module outside the local model client imports a library
that can talk to the network or send mail. It cannot prove the rule, but it makes breaking it
a deliberate act with a visible test change.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "citetally"

FORBIDDEN = {
    "smtplib", "imaplib", "poplib", "ftplib", "telnetlib", "nntplib", "xmlrpc", "socketserver",
    "socket", "ssl", "http.client", "urllib.request", "urllib3", "requests", "httpx", "httpx2",
    "aiohttp", "websockets", "paramiko", "boto3", "email.mime",
}  # fmt: skip

# The one module allowed to open a connection: it talks to Ollama on this machine (providers/).
ALLOWED = {PACKAGE / "providers" / "ollama.py"}


def imported_modules(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_only_the_local_model_client_imports_anything_that_can_send() -> None:
    offenders = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        if path in ALLOWED:
            continue
        hits = sorted(
            name
            for name in imported_modules(path)
            if any(name == bad or name.startswith(bad + ".") for bad in FORBIDDEN)
        )
        if hits:
            offenders[str(path.relative_to(PACKAGE))] = hits
    assert offenders == {}, "these modules import something that can send: " + repr(offenders)


def test_the_export_module_writes_a_file_and_nothing_else() -> None:
    names = imported_modules(PACKAGE / "export.py")
    assert not {n for n in names if n.split(".")[0] in {"smtplib", "urllib", "http", "socket"}}
