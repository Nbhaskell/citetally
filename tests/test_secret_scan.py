"""The secret-scan wrapper: pure parts only. The real gitleaks binary is never run here."""

import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools.secret_scan import (
    PINNED_SHA256,
    VERSION,
    ChecksumError,
    asset_name,
    extract_binary,
    find_binary,
    local_binary,
    main,
    scan_command,
    verify_checksum,
)


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Windows", "AMD64", f"gitleaks_{VERSION}_windows_x64.zip"),
        ("Linux", "x86_64", f"gitleaks_{VERSION}_linux_x64.tar.gz"),
        ("Linux", "aarch64", f"gitleaks_{VERSION}_linux_arm64.tar.gz"),
        ("Darwin", "arm64", f"gitleaks_{VERSION}_darwin_arm64.tar.gz"),
    ],
)
def test_asset_name_matches_the_release_naming(system: str, machine: str, expected: str) -> None:
    assert asset_name(system, machine) == expected


def test_asset_name_rejects_unknown_platforms() -> None:
    with pytest.raises(ValueError, match="platform"):
        asset_name("Plan9", "mips")


def test_verify_checksum_accepts_a_match_and_rejects_a_mismatch() -> None:
    data = b"binary bytes"
    verify_checksum(data, hashlib.sha256(data).hexdigest())
    with pytest.raises(ChecksumError):
        verify_checksum(data, "0" * 64)


def make_zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def make_tar(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_extract_binary_from_zip_and_tar_ignores_other_members() -> None:
    zipped = make_zip({"LICENSE": b"mit", "README.md": b"hi", "gitleaks.exe": b"EXE"})
    tarred = make_tar({"LICENSE": b"mit", "gitleaks": b"ELF"})
    assert extract_binary("gitleaks_x_windows_x64.zip", zipped) == b"EXE"
    assert extract_binary("gitleaks_x_linux_x64.tar.gz", tarred) == b"ELF"


def test_extract_binary_never_uses_the_path_inside_the_archive() -> None:
    # A hostile archive cannot choose where the file goes: only its bytes are returned.
    tarred = make_tar({"../../evil/gitleaks": b"ELF"})
    assert extract_binary("gitleaks_x_linux_x64.tar.gz", tarred) == b"ELF"


def test_extract_binary_fails_when_the_binary_is_missing() -> None:
    with pytest.raises(ValueError, match="gitleaks"):
        extract_binary("gitleaks_x_linux_x64.tar.gz", make_tar({"LICENSE": b"mit"}))


def test_local_binary_lives_in_the_ignored_tools_folder(tmp_path: Path) -> None:
    assert local_binary(tmp_path, "Windows") == tmp_path / ".tools" / "gitleaks" / "gitleaks.exe"
    assert local_binary(tmp_path, "Linux") == tmp_path / ".tools" / "gitleaks" / "gitleaks"


def test_find_binary_prefers_the_pinned_local_copy(tmp_path: Path) -> None:
    local = local_binary(tmp_path, "Linux")
    found = find_binary(
        tmp_path, "Linux", which=lambda _: "/usr/bin/gitleaks", exists=lambda p: p == local
    )
    assert found == str(local)


def test_find_binary_falls_back_to_path_then_to_none(tmp_path: Path) -> None:
    assert find_binary(
        tmp_path, "Linux", which=lambda _: "/usr/bin/gitleaks", exists=lambda _: False
    )
    assert find_binary(tmp_path, "Linux", which=lambda _: None, exists=lambda _: False) is None


def test_scan_commands_redact_and_use_the_repo_config() -> None:
    staged = scan_command("gl", "staged", "cfg.toml")
    history = scan_command("gl", "history", "cfg.toml")
    for command in (staged, history):
        assert command[:2] == ["gl", "git"]
        assert "--redact" in command  # a found secret is never printed
        assert command[command.index("--config") + 1] == "cfg.toml"
    assert "--staged" in staged
    assert "--staged" not in history


def test_main_blocks_when_gitleaks_is_missing(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--staged"], find=lambda: None, run=lambda _: 0)
    assert code == 1
    assert "secret_scan.py --fetch" in capsys.readouterr().out


def test_main_passes_the_scanner_exit_code_through(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--history"], find=lambda: "gl", run=lambda _: 0) == 0
    assert "No secrets found" in capsys.readouterr().out
    assert main(["--staged"], find=lambda: "gl", run=lambda _: 1) == 1
    assert "Secret scan failed" in capsys.readouterr().out


def test_main_needs_exactly_one_mode() -> None:
    with pytest.raises(SystemExit):
        main([], find=lambda: "gl", run=lambda _: 0)


def test_every_supported_platform_has_a_pinned_checksum() -> None:
    for system, machine in [
        ("Windows", "AMD64"),
        ("Windows", "ARM64"),
        ("Linux", "x86_64"),
        ("Linux", "aarch64"),
        ("Darwin", "x86_64"),
        ("Darwin", "arm64"),
    ]:
        sha = PINNED_SHA256[asset_name(system, machine)]
        assert len(sha) == 64
        int(sha, 16)
