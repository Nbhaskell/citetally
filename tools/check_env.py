"""Report whether this machine is ready to run Citetally.

Run from the repository root:  python tools/check_env.py   (add --strict to exit 1 on problems)

Uses only the standard library so it works before the virtual environment exists. It reports
problems and prints Windows install hints; it never installs anything and exits 0 unless
--strict is given, so it can never fail the test suite.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_TEXT_MODEL = "qwen3:8b"
DEFAULT_VISION_MODEL = "qwen3-vl:8b-instruct"
REQUIRED_PYTHON = (3, 13)

TESSERACT_HINT = (
    "winget install --id UB-Mannheim.TesseractOCR  (then open a new terminal; if it is still "
    "not found, set TESSERACT_CMD in .env to the full path of tesseract.exe)"
)
OLLAMA_INSTALL_HINT = (
    "winget install --id Ollama.Ollama  (then start Ollama and run: ollama pull qwen3:8b)"
)
OLLAMA_START_HINT = (
    "Ollama is installed but not answering. Start the Ollama app, or run: ollama serve"
)
PYTHON_HINT = "winget install --id Python.Python.3.13  (the project needs Python 3.13)"
NODE_HINT = "winget install --id OpenJS.NodeJS.LTS  (the web app needs Node.js 20.19 or newer)"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    hint: str = ""


@dataclass(frozen=True)
class Probes:
    """Everything that touches the machine, so tests can replace it."""

    which: Callable[[str], str | None]
    exists: Callable[[str], bool]
    run: Callable[[list[str]], str]
    fetch_json: Callable[[str], Mapping[str, object]]
    python_version: tuple[int, int, int]


def _run(args: list[str]) -> str:
    done = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
    return (done.stdout + done.stderr).strip()


def _fetch_json(url: str) -> dict[str, object]:
    if not url.startswith(("http://", "https://")):
        raise ValueError("OLLAMA_URL must start with http:// or https://")
    with urllib.request.urlopen(url, timeout=3) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise ValueError("unexpected reply")
    return data


def default_probes() -> Probes:
    info = sys.version_info
    return Probes(
        which=shutil.which,
        exists=os.path.exists,
        run=_run,
        fetch_json=_fetch_json,
        python_version=(info.major, info.minor, info.micro),
    )


def load_dotenv(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines. Blank values are skipped, like the app's settings do."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip("\"'").strip()
        if key.strip() and value:
            values[key.strip()] = value
    return values


def _check_python(probes: Probes) -> Check:
    major, minor, micro = probes.python_version
    found = f"{major}.{minor}.{micro}"
    if (major, minor) == REQUIRED_PYTHON:
        return Check("Python", True, found)
    return Check("Python", False, f"{found} (need 3.13)", PYTHON_HINT)


def _check_node(probes: Probes) -> Check:
    path = probes.which("node")
    if not path:
        return Check("Node.js", False, "not found", NODE_HINT)
    try:
        return Check("Node.js", True, probes.run([path, "--version"]).splitlines()[0])
    except Exception as error:
        return Check("Node.js", False, f"found but would not run ({type(error).__name__})")


def _find_tesseract(env: Mapping[str, str], probes: Probes) -> str | None:
    configured = env.get("TESSERACT_CMD", "")
    if configured:
        return configured if probes.exists(configured) or probes.which(configured) else None
    on_path = probes.which("tesseract")
    if on_path:
        return on_path
    defaults = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    if env.get("LOCALAPPDATA"):
        defaults.append(rf"{env['LOCALAPPDATA']}\Programs\Tesseract-OCR\tesseract.exe")
    return next((path for path in defaults if probes.exists(path)), None)


def _check_tesseract(env: Mapping[str, str], probes: Probes) -> Check:
    exe = _find_tesseract(env, probes)
    if exe is None:
        return Check("Tesseract", False, "not found", TESSERACT_HINT)
    try:
        version = probes.run([exe, "--version"]).splitlines()[0]
        langs = probes.run([exe, "--list-langs"]).split()
    except Exception as error:
        detail = f"found but would not run ({type(error).__name__})"
        return Check("Tesseract", False, detail, TESSERACT_HINT)
    if "eng" not in langs:
        detail = f"{version}, but the English data (eng) is missing"
        return Check("Tesseract", False, detail, TESSERACT_HINT)
    return Check("Tesseract", True, f"{version} at {exe}")


def _pulled_models(reply: Mapping[str, object]) -> list[str]:
    models = reply.get("models")
    if not isinstance(models, list):
        raise ValueError("unexpected reply")
    names: list[str] = []
    for item in models:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("unexpected reply")
        names.append(item["name"])
    return names


def _check_ollama(env: Mapping[str, str], probes: Probes) -> list[Check]:
    url = env.get("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")
    try:
        names = _pulled_models(probes.fetch_json(f"{url}/api/tags"))
    except Exception as error:
        hint = OLLAMA_START_HINT if probes.which("ollama") else OLLAMA_INSTALL_HINT
        return [Check("Ollama", False, f"not reachable at {url} ({type(error).__name__})", hint)]

    pulled = ", ".join(names) if names else "none"
    checks = [Check("Ollama", True, f"reachable at {url}; models pulled: {pulled}")]
    text = env.get("CITETALLY_TEXT_MODEL", DEFAULT_TEXT_MODEL)
    vision = env.get("CITETALLY_VISION_MODEL", DEFAULT_VISION_MODEL)
    for model in [text, *([vision] if vision else [])]:
        present = model in names or (":" not in model and f"{model}:latest" in names)
        optional = model == vision and model != text
        missing = "not pulled" + (
            " (scans and photos are read as text only without it)" if optional else ""
        )
        checks.append(
            Check(
                f"Ollama model {model}",
                present,
                "pulled" if present else missing,
                "" if present else f"ollama pull {model}",
            )
        )
    return checks


def run_checks(env: Mapping[str, str], probes: Probes) -> list[Check]:
    return [
        _check_python(probes),
        _check_node(probes),
        _check_tesseract(env, probes),
        *_check_ollama(env, probes),
    ]


def render_report(checks: Sequence[Check]) -> str:
    title = "Citetally environment check"
    lines = [title, "=" * len(title), ""]
    for check in checks:
        status = "[ok]" if check.ok else "[missing]"
        lines.append(f"{status:<10}{check.name:<28}{check.detail}")
    problems = [c for c in checks if not c.ok]
    if problems:
        lines += ["", "How to fix", "----------"]
        lines += [f"{c.name}: {c.hint}" for c in problems if c.hint]
    else:
        lines += ["", "Everything needed for the current phase is in place."]
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    probes: Probes | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Check the Citetally development environment.")
    parser.add_argument("--strict", action="store_true", help="exit 1 if anything is missing")
    args = parser.parse_args(argv)

    if env is None:
        repo_root = Path(__file__).resolve().parent.parent
        env = {**load_dotenv(repo_root / ".env"), **os.environ}
    checks = run_checks(env, probes or default_probes())
    print(render_report(checks))
    return 1 if args.strict and any(not c.ok for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
