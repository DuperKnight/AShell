from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_OWNER = "DuperKnight"
REPO_NAME = "AShell"
TAGS_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/tags"

_LATEST_RELEASE_CACHE: tuple[str, str] | None = None


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"


def _parse_version(raw: str) -> tuple[int, int, int] | None:
    cleaned = raw.strip()
    if cleaned.startswith(("v", "V")):
        cleaned = cleaned[1:]
    parts = cleaned.split(".")
    if len(parts) < 3:
        return None
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
    except ValueError:
        return None
    return major, minor, patch


def _compare_versions(left: str, right: str) -> int:
    parsed_left = _parse_version(left)
    parsed_right = _parse_version(right)
    if parsed_left is None or parsed_right is None:
        raise ValueError("Unparseable version string")
    if parsed_left > parsed_right:
        return 1
    if parsed_left < parsed_right:
        return -1
    return 0


def format_version_for_display(version: str) -> str:
    stripped = version.strip()
    if stripped.lower().startswith("v"):
        return stripped
    return f"v{stripped}"


def fetch_latest_release_info(force_refresh: bool = False) -> tuple[str, str] | None:
    global _LATEST_RELEASE_CACHE
    if not force_refresh and _LATEST_RELEASE_CACHE is not None:
        return _LATEST_RELEASE_CACHE

    request = urllib.request.Request(
        TAGS_API_URL,
        headers={"User-Agent": "AShell"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    if not isinstance(data, list):
        return None

    best_numeric: tuple[int, int, int] | None = None
    best_entry: tuple[str, str] | None = None

    for entry in data:
        tag_name = entry.get("name")
        zip_url = entry.get("zipball_url")
        if not isinstance(tag_name, str) or not isinstance(zip_url, str):
            continue
        parsed = _parse_version(tag_name)
        if parsed is None:
            continue
        if best_numeric is None or parsed > best_numeric:
            best_numeric = parsed
            best_entry = (tag_name, zip_url)

    if best_entry is not None:
        _LATEST_RELEASE_CACHE = best_entry
        return best_entry
    return None


def check_for_newer_version(current_version: str, *, force_refresh: bool = False) -> tuple[str, str] | None:
    release = fetch_latest_release_info(force_refresh=force_refresh)
    if not release:
        return None
    latest_version, _ = release
    try:
        if _compare_versions(latest_version, current_version) <= 0:
            return None
    except ValueError:
        return None
    return release


def _download_release_archive(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "AShell"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _extract_release_archive(archive_path: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(destination)
        top_level: Path | None = None
        for member in archive.namelist():
            name = member.split("/", 1)[0]
            if name and not name.startswith("__MACOSX"):
                top_level = destination / name
                break
    if top_level and top_level.exists():
        return top_level
    raise RuntimeError("Unable to locate extracted release root")


def _copy_release_contents(source_root: Path, target_root: Path) -> None:
    for item in source_root.iterdir():
        target = target_root / item.name
        if item.is_dir():
            if target.exists() and target.is_file():
                target.unlink()
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            if target.exists() and target.is_dir():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _install_requirements(install_dir: Path) -> bool:
    requirements = install_dir / "requirements.txt"
    if not requirements.exists():
        return True

    print("Updating Python dependencies...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"AShell: pip install failed (exit code {exc.returncode}).")
        return False
    return True


def perform_upgrade(current_version: str, *, install_dir: Path | None = None) -> int:
    print(f"{Colors.BOLD}Checking for updates...{Colors.RESET}")
    release = fetch_latest_release_info(force_refresh=True)
    if not release:
        print("AShell: Could not retrieve release information from GitHub.")
        return 1

    latest_version, zip_url = release
    try:
        comparison = _compare_versions(latest_version, current_version)
    except ValueError:
        print("AShell: Unable to compare version numbers.")
        return 1

    if comparison <= 0:
        print("AShell is already up to date.")
        return 0

    display_latest = format_version_for_display(latest_version)
    display_current = format_version_for_display(current_version)
    print(f"Upgrading AShell from {display_current} to {display_latest}...")

    install_root = install_dir or Path(__file__).resolve().parent
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            archive_path = tmp_path / "ashell.zip"
            _download_release_archive(zip_url, archive_path)
            extracted_root = _extract_release_archive(archive_path, tmp_path / "src")
            _copy_release_contents(extracted_root, install_root)
    except (urllib.error.URLError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"AShell: Upgrade failed: {exc}")
        return 1

    if not _install_requirements(install_root):
        return 1

    print(
        f"{Colors.GREEN}{Colors.BOLD}Upgrade complete.{Colors.RESET} "
        f"Restart AShell to use {display_latest} (reload -full)."
    )
    return 0


__all__ = [
    "check_for_newer_version",
    "fetch_latest_release_info",
    "format_version_for_display",
    "perform_upgrade",
]
