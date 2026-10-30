"""check_env must report problems, never raise them, and never touch the network in tests."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tools.check_env import (
    Check,
    Probes,
    load_dotenv,
    main,
    render_report,
    run_checks,
)

TESSERACT_VERSION = "tesseract 5.5.0\n leptonica-1.85.0"
GOOD_TAGS = {"models": [{"name": "qwen3:8b"}, {"name": "llava:7b"}]}


def make_probes(
    *,
    on_path: dict[str, str] | None = None,
    existing: set[str] | None = None,
    commands: dict[str, str] | None = None,
    tags: Mapping[str, object] | Exception | None = None,
    python: tuple[int, int, int] = (3, 13, 1),
) -> Probes:
    on_path = on_path or {}
    existing = existing or set()
    commands = commands or {}

    def run(args: list[str]) -> str:
        key = " ".join(args)
        if key not in commands:
            raise FileNotFoundError(args[0])
        return commands[key]

    def fetch_json(url: str) -> Mapping[str, object]:
        assert url.endswith("/api/tags")
        if tags is None or isinstance(tags, Exception):
            raise tags or ConnectionRefusedError("refused")
        return tags

    return Probes(
        which=lambda name: on_path.get(name),
        exists=lambda path: path in existing,
        run=run,
        fetch_json=fetch_json,
        python_version=python,
    )


def by_name(checks: list[Check]) -> dict[str, Check]:
    return {c.name: c for c in checks}


def healthy_probes() -> Probes:
    return make_probes(
        on_path={"tesseract": "C:/tess/tesseract.exe", "ollama": "C:/ollama.exe", "node": "node"},
        commands={
            "C:/tess/tesseract.exe --version": TESSERACT_VERSION,
            "C:/tess/tesseract.exe --list-langs": "List of available languages (2):\neng\nosd\n",
            "node --version": "v24.20.0",
        },
        tags=GOOD_TAGS,
    )


def test_everything_present_reports_ok() -> None:
    checks = by_name(run_checks({}, healthy_probes()))
    assert all(c.ok for c in checks.values()), checks
    assert "5.5.0" in checks["Tesseract"].detail


def test_missing_tesseract_gives_a_windows_install_hint() -> None:
    checks = by_name(run_checks({}, make_probes(tags=GOOD_TAGS)))
    tesseract = checks["Tesseract"]
    assert not tesseract.ok
    assert "winget install" in tesseract.hint
    assert "TESSERACT_CMD" in tesseract.hint


def test_tesseract_found_in_default_windows_folder() -> None:
    exe = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    probes = make_probes(
        existing={exe},
        commands={f"{exe} --version": TESSERACT_VERSION, f"{exe} --list-langs": "eng\n"},
        tags=GOOD_TAGS,
    )
    assert by_name(run_checks({}, probes))["Tesseract"].ok


def test_tesseract_cmd_setting_wins_over_path() -> None:
    probes = make_probes(
        on_path={"tesseract": "C:/other/tesseract.exe"},
        existing={"D:/custom/tesseract.exe"},
        commands={
            "D:/custom/tesseract.exe --version": "tesseract 5.3.0",
            "D:/custom/tesseract.exe --list-langs": "eng\n",
        },
        tags=GOOD_TAGS,
    )
    check = by_name(run_checks({"TESSERACT_CMD": "D:/custom/tesseract.exe"}, probes))["Tesseract"]
    assert check.ok
    assert "5.3.0" in check.detail


def test_tesseract_without_english_data_is_not_ok() -> None:
    probes = make_probes(
        on_path={"tesseract": "t"},
        commands={"t --version": TESSERACT_VERSION, "t --list-langs": "osd\n"},
        tags=GOOD_TAGS,
    )
    check = by_name(run_checks({}, probes))["Tesseract"]
    assert not check.ok
    assert "eng" in check.detail


def test_ollama_unreachable_when_not_installed() -> None:
    check = by_name(run_checks({}, make_probes()))["Ollama"]
    assert not check.ok
    assert "winget install" in check.hint
    assert "ollama pull qwen3:8b" in check.hint


def test_ollama_installed_but_not_running_says_to_start_it() -> None:
    check = by_name(run_checks({}, make_probes(on_path={"ollama": "C:/ollama.exe"})))["Ollama"]
    assert not check.ok
    assert "start" in check.hint.lower()
    assert "winget install" not in check.hint


def test_missing_text_model_gives_a_pull_command() -> None:
    probes = make_probes(tags={"models": [{"name": "llava:7b"}]})
    checks = by_name(run_checks({}, probes))
    assert checks["Ollama"].ok
    assert "llava:7b" in checks["Ollama"].detail
    model = checks["Ollama model qwen3:8b"]
    assert not model.ok
    assert model.hint == "ollama pull qwen3:8b"


def test_configured_model_names_are_respected() -> None:
    env = {"CITETALLY_TEXT_MODEL": "other:1b", "CITETALLY_VISION_MODEL": "llava:7b"}
    checks = by_name(run_checks(env, make_probes(tags={"models": [{"name": "llava:7b"}]})))
    assert not checks["Ollama model other:1b"].ok
    assert checks["Ollama model llava:7b"].ok
    assert "Ollama model qwen3:8b" not in checks


def test_vision_model_is_skipped_when_unset() -> None:
    checks = by_name(run_checks({}, healthy_probes()))
    assert not any("vision" in name.lower() for name in checks)


def test_malformed_ollama_reply_is_reported_not_raised() -> None:
    check = by_name(run_checks({}, make_probes(tags={"models": "nope"})))["Ollama"]
    assert not check.ok


def test_wrong_python_version_is_flagged() -> None:
    check = by_name(run_checks({}, make_probes(python=(3, 11, 9))))["Python"]
    assert not check.ok
    assert "3.13" in check.hint


def test_report_is_readable_and_lists_hints_for_failures() -> None:
    report = render_report(run_checks({}, make_probes()))
    assert "[ok]" in report
    assert "[missing]" in report
    assert "How to fix" in report
    assert "winget install" in report


def test_report_has_no_fix_section_when_everything_is_ok() -> None:
    assert "How to fix" not in render_report(run_checks({}, healthy_probes()))


def test_main_exits_zero_even_when_everything_is_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([], env={}, probes=make_probes()) == 0
    assert "Citetally environment check" in capsys.readouterr().out


def test_main_strict_exits_one_when_something_is_missing() -> None:
    assert main(["--strict"], env={}, probes=make_probes()) == 1
    assert main(["--strict"], env={}, probes=healthy_probes()) == 0


def test_load_dotenv_reads_simple_lines(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        '# comment\nOLLAMA_URL=http://127.0.0.1:1234\nCITETALLY_TEXT_MODEL="m:1"\n'
        "EMPTY=\nTESSERACT_CMD='C:/x y/t.exe'  \nnot a pair\n",
        encoding="utf-8",
    )
    assert load_dotenv(path) == {
        "OLLAMA_URL": "http://127.0.0.1:1234",
        "CITETALLY_TEXT_MODEL": "m:1",
        "TESSERACT_CMD": "C:/x y/t.exe",
    }


def test_load_dotenv_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_dotenv(tmp_path / "nope.env") == {}
