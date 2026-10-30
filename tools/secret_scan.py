"""Scan for committed secrets with gitleaks, using a pinned copy kept inside the project.

  python tools/secret_scan.py --fetch     download the pinned gitleaks into .tools/ (git-ignored)
  python tools/secret_scan.py --staged    scan what is staged for commit (the pre-commit hook)
  python tools/secret_scan.py --history   scan the whole git history (CI, and before publishing)

gitleaks (MIT) is a single binary. The download comes from the project's own GitHub release and
is checked against the SHA-256 values pinned below, so nothing is installed system-wide and a
tampered download is refused. Findings are redacted: a found secret is never printed. The rule
set is gitleaks' built-in one, extended by .gitleaks.toml (see that file before allowlisting
anything). To change the version, update VERSION and PINNED_SHA256 from the release's
checksums file.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

VERSION = "8.30.1"
RELEASE_URL = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/"
_SHA256_BY_PLATFORM = {
    "darwin_arm64.tar.gz": "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
    "darwin_x64.tar.gz": "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709",
    "linux_arm64.tar.gz": "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080",
    "linux_x64.tar.gz": "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
    "windows_arm64.zip": "b95f5e4f5c425cedca7ee203d9afd29597e692c4924a12ed42f970537c72cc0f",
    "windows_x64.zip": "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e",
}
PINNED_SHA256 = {f"gitleaks_{VERSION}_{k}": v for k, v in _SHA256_BY_PLATFORM.items()}
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = ".gitleaks.toml"


class ChecksumError(Exception):
    """The downloaded file does not match the pinned checksum."""


def asset_name(system: str, machine: str) -> str:
    os_name = {"windows": "windows", "linux": "linux", "darwin": "darwin"}.get(system.lower())
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        machine.lower()
    )
    if os_name is None or arch is None:
        raise ValueError(f"No gitleaks build is pinned for this platform: {system} {machine}")
    extension = "zip" if os_name == "windows" else "tar.gz"
    return f"gitleaks_{VERSION}_{os_name}_{arch}.{extension}"


def verify_checksum(data: bytes, expected: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected.lower():
        raise ChecksumError("The download does not match the pinned SHA-256; it was not used.")


def extract_binary(asset: str, data: bytes) -> bytes:
    """Return the bytes of the gitleaks executable. The path inside the archive is never used."""
    wanted = {"gitleaks", "gitleaks.exe"}
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if Path(info.filename).name in wanted:
                    return archive.read(info)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.isfile() and Path(member.name).name in wanted:
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        return extracted.read()
    raise ValueError("The archive does not contain a gitleaks executable.")


def local_binary(root: Path, system: str) -> Path:
    name = "gitleaks.exe" if system.lower() == "windows" else "gitleaks"
    return root / ".tools" / "gitleaks" / name


def find_binary(
    root: Path,
    system: str,
    which: Callable[[str], str | None] = shutil.which,
    exists: Callable[[Path], bool] = Path.is_file,
) -> str | None:
    """The pinned local copy if present, else any gitleaks on PATH, else None."""
    local = local_binary(root, system)
    if exists(local):
        return str(local)
    return which("gitleaks")


def scan_command(binary: str, mode: str, config: str) -> list[str]:
    command = [binary, "git", "--no-banner", "--redact", "--config", config]
    if mode == "staged":
        command.append("--staged")
    return command


def fetch(root: Path = REPO_ROOT) -> Path:
    """Download, verify and place the pinned binary under .tools/gitleaks/."""
    asset = asset_name(platform.system(), platform.machine())
    if not RELEASE_URL.startswith("https://"):
        raise ValueError("The release URL must be https.")
    with urllib.request.urlopen(RELEASE_URL + asset, timeout=60) as response:
        data = response.read()
    verify_checksum(data, PINNED_SHA256[asset])
    target = local_binary(root, platform.system())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(extract_binary(asset, data))
    target.chmod(0o755)
    return target


def _run(command: list[str]) -> int:
    return subprocess.run(command, cwd=REPO_ROOT, check=False).returncode


def main(
    argv: Sequence[str] | None = None,
    find: Callable[[], str | None] | None = None,
    run: Callable[[list[str]], int] = _run,
) -> int:
    parser = argparse.ArgumentParser(description="Scan for committed secrets with gitleaks.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch", action="store_true", help="download the pinned gitleaks")
    mode.add_argument("--staged", action="store_true", help="scan staged changes")
    mode.add_argument("--history", action="store_true", help="scan the whole git history")
    args = parser.parse_args(argv)

    if args.fetch:
        try:
            print(f"Installed gitleaks {VERSION} at {fetch()}")
        except (ValueError, ChecksumError, OSError) as error:
            print(f"Could not fetch gitleaks: {error}")
            return 1
        return 0

    binary = (find or (lambda: find_binary(REPO_ROOT, platform.system())))()
    if binary is None:
        print("gitleaks was not found, so the secret scan did not run.")
        print("Fetch the pinned copy into the project with: python tools/secret_scan.py --fetch")
        return 1
    code = run(scan_command(binary, "staged" if args.staged else "history", CONFIG))
    if code != 0:
        print("Secret scan failed: see the redacted findings above, or the error from gitleaks.")
        return 1
    print("No secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
