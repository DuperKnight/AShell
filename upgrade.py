from __future__ import annotations

import json
import re
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

RELEASE_BY_TAG_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/tags/{{tag}}"
)
CHANGELOG_DIR = Path.home() / ".ashell" / "changelogs"
PENDING_CHANGELOG_PATH = Path.home() / ".ashell" / ".pending_changelog"
_RELEASE_NOTE_CACHE: dict[str, str] = {}
CHANGELOG_RAW_URL_TEMPLATE = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{{ref}}/{{filename}}"
)
CHANGELOG_FILES: tuple[str, ...] = (
    "CHANGELOG.md",
    "docs/CHANGELOG.md",
    "changelog.md",
)
CHANGELOG_FALLBACK_REFS: tuple[str, ...] = ("main", "master")


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"


_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^\)]+)\)")
_BOLD_PATTERN = re.compile(r"\*\*([^*]+)\*\*")
_UNDERLINE_PATTERN = re.compile(r"__([^_]+)__")
_ITALIC_PATTERN = re.compile(r"(?<!\*)\*(?!\s)([^*]+?)(?<!\s)\*(?!\*)")
_CODE_PATTERN = re.compile(r"`([^`]+)`")
_GITHUB_COMMIT_URL = re.compile(
    r"https://github\.com/([^/\s]+)/([^/\s]+)/commit/([0-9a-fA-F]{7,40})",
    re.IGNORECASE,
)
_GITHUB_COMPARE_URL = re.compile(
    r"https://github\.com/([^/\s]+)/([^/\s]+)/compare/([0-9A-Za-z_.-]+)\.\.\.([0-9A-Za-z_.-]+)",
    re.IGNORECASE,
)


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


def _normalize_version_input(version: str) -> tuple[str, str]:
    cleaned = (version or "").strip()
    if not cleaned:
        raise ValueError("Version string is empty")
    canonical = cleaned[1:] if cleaned.lower().startswith("v") else cleaned
    display_tag = format_version_for_display(canonical)
    return canonical, display_tag


def _tag_candidates(canonical: str, display_tag: str) -> tuple[str, ...]:
    candidates = [canonical]
    if display_tag and display_tag != canonical:
        candidates.append(display_tag)
    return tuple(dict.fromkeys(candidates))


def _changelog_path(tag: str) -> Path:
    return CHANGELOG_DIR / f"{tag}.md"


def _ensure_changelog_dir() -> None:
    CHANGELOG_DIR.mkdir(parents=True, exist_ok=True)


def _cache_changelog(primary_tag: str, alternate_tag: str | None, content: str) -> Path | None:
    try:
        _ensure_changelog_dir()
        path = _changelog_path(primary_tag)
        path.write_text(content, encoding="utf-8")
        if alternate_tag and alternate_tag != primary_tag:
            legacy_path = _changelog_path(alternate_tag)
            if legacy_path != path and legacy_path.exists():
                try:
                    legacy_path.unlink()
                except OSError:
                    pass
        return path
    except OSError:
        return None


def get_cached_changelog(version: str) -> str | None:
    try:
        canonical, display_tag = _normalize_version_input(version)
    except ValueError:
        return None
    for candidate in _tag_candidates(canonical, display_tag):
        path = _changelog_path(candidate)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except OSError:
            return None
    return None


def fetch_release_notes(tag_candidates: tuple[str, ...], *, force_refresh: bool = False) -> str | None:
    fresh_candidates = [tag for tag in tag_candidates if tag]
    if not fresh_candidates:
        return None

    if not force_refresh:
        for tag in fresh_candidates:
            cached = _RELEASE_NOTE_CACHE.get(tag)
            if cached is not None:
                return cached

    for tag in fresh_candidates:
        url = RELEASE_BY_TAG_URL.format(tag=tag)
        request = urllib.request.Request(url, headers={"User-Agent": "AShell"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        body = data.get("body") if isinstance(data, dict) else None
        if isinstance(body, str) and body.strip():
            _RELEASE_NOTE_CACHE[tag] = body
            return body
    return None


def _download_raw_changelog(ref: str) -> str | None:
    for filename in CHANGELOG_FILES:
        url = CHANGELOG_RAW_URL_TEMPLATE.format(ref=ref, filename=filename)
        request = urllib.request.Request(url, headers={"User-Agent": "AShell"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError):
            continue
    return None


def _format_inline_markdown(text: str) -> str:
    def _link_replacer(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        target = match.group(2).strip()
        if not label:
            return target
        if label == target:
            return target
        return f"{label} ({target})"

    text = _LINK_PATTERN.sub(_link_replacer, text)
    text = _CODE_PATTERN.sub(lambda m: f"{Colors.YELLOW}{m.group(1)}{Colors.RESET}", text)
    text = _BOLD_PATTERN.sub(lambda m: f"{Colors.BOLD}{m.group(1)}{Colors.RESET}", text)
    text = _UNDERLINE_PATTERN.sub(lambda m: f"{Colors.BOLD}{m.group(1)}{Colors.RESET}", text)
    text = _ITALIC_PATTERN.sub(lambda m: f"{Colors.YELLOW}{m.group(1)}{Colors.RESET}", text)
    return _shorten_github_urls(text)


def _shorten_github_urls(text: str) -> str:
    def _hyperlink(label: str, url: str) -> str:
        return f"\033]8;;{url}\033\\{label}\033]8;;\033\\"

    def _commit_replacer(match: re.Match[str]) -> str:
        repo = match.group(2)
        sha = match.group(3)
        short_sha = sha[:7]
        label = f"{Colors.YELLOW}{repo}@{short_sha}{Colors.RESET}"
        return _hyperlink(label, match.group(0))

    def _compare_replacer(match: re.Match[str]) -> str:
        repo = match.group(2)
        base = match.group(3)
        head = match.group(4)
        display_base = base if len(base) <= 12 else f"{base[:4]}…{base[-4:]}"
        display_head = head if len(head) <= 12 else f"{head[:4]}…{head[-4:]}"
        label = f"{repo}:{display_base}->{display_head}"
        return _hyperlink(label, match.group(0))

    text = _GITHUB_COMMIT_URL.sub(_commit_replacer, text)
    text = _GITHUB_COMPARE_URL.sub(_compare_replacer, text)
    return text


def _extract_changelog_section(raw_text: str, canonical: str, display_tag: str) -> str | None:
    headings = list(re.finditer(r"^##\s+(.+)$", raw_text, flags=re.MULTILINE))
    if not headings:
        return None

    search_terms = {
        canonical.lower(),
        display_tag.lower(),
        canonical.lstrip("v").lower(),
        display_tag.lstrip("v").lower(),
    }
    stripped_terms = {term.lstrip("v") for term in search_terms}

    for idx, match in enumerate(headings):
        heading_text = match.group(1).strip()
        heading_plain = heading_text.replace("[", "").replace("]", "")
        heading_tokens = heading_plain.split()
        primary = heading_tokens[0] if heading_tokens else heading_plain
        normalized_primary = primary.lstrip("v").lower()
        heading_lower = heading_plain.lower()

        if any(term and term in heading_lower for term in search_terms) or (
            normalized_primary and normalized_primary in stripped_terms
        ):
            start = match.end()
            end = headings[idx + 1].start() if idx + 1 < len(headings) else len(raw_text)
            section = raw_text[start:end].strip()
            return section
    return None


def _fetch_changelog_from_repository(
    canonical: str,
    display_tag: str,
    tag_candidates: tuple[str, ...],
) -> str | None:

    ref_candidates = list(tag_candidates)
    ref_candidates.extend(CHANGELOG_FALLBACK_REFS)

    seen: set[str] = set()
    fallback_raw: str | None = None
    for ref in ref_candidates:
        if not ref or ref in seen:
            continue
        seen.add(ref)
        raw = _download_raw_changelog(ref)
        if not raw:
            continue
        if fallback_raw is None:
            fallback_raw = raw
        section = _extract_changelog_section(raw, canonical, display_tag)
        if section:
            return section
    return fallback_raw


def fetch_and_cache_changelog(version: str, *, force_refresh: bool = False) -> str | None:
    try:
        canonical, display_tag = _normalize_version_input(version)
    except ValueError:
        return None
    tag_candidates = _tag_candidates(canonical, display_tag)
    content = fetch_release_notes(tag_candidates, force_refresh=force_refresh)
    if not content:
        content = _fetch_changelog_from_repository(canonical, display_tag, tag_candidates)
    if not content:
        return None
    primary_tag = tag_candidates[0]
    alternate_tag = tag_candidates[1] if len(tag_candidates) > 1 else None
    _cache_changelog(primary_tag, alternate_tag, content)
    return content


def get_changelog_for_version(version: str, *, allow_fetch: bool = True) -> str | None:
    cached = get_cached_changelog(version)
    if cached is not None:
        return cached
    if not allow_fetch:
        return None
    return fetch_and_cache_changelog(version)


def set_pending_changelog(version: str) -> None:
    try:
        canonical, _ = _normalize_version_input(version)
    except ValueError:
        return
    try:
        PENDING_CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        PENDING_CHANGELOG_PATH.write_text(canonical, encoding="utf-8")
    except OSError:
        pass


def render_markdown_for_terminal(markdown_text: str) -> str:
    if not markdown_text:
        return ""

    rendered_lines: list[str] = []
    previous_blank = True

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            if not previous_blank:
                rendered_lines.append("")
                previous_blank = True
            continue

        heading_match = re.match(r"^(#{1,6})\s*(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            content = _format_inline_markdown(heading_match.group(2).strip())
            if level <= 2:
                content = content.upper()
            decorated = f"{Colors.BOLD}{content}{Colors.RESET}"
            if not previous_blank:
                rendered_lines.append("")
            rendered_lines.append(decorated)
            previous_blank = False
            continue

        bullet_match = re.match(r"^[-*+]\s+(.*)$", stripped)
        if bullet_match:
            content = _format_inline_markdown(bullet_match.group(1).strip())
            rendered_lines.append(f"- {content}")
            previous_blank = False
            continue

        numbered_match = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if numbered_match:
            index = numbered_match.group(1)
            content = _format_inline_markdown(numbered_match.group(2).strip())
            rendered_lines.append(f"{index}. {content}")
            previous_blank = False
            continue

        blockquote_match = re.match(r"^>\s?(.*)$", stripped)
        if blockquote_match:
            content = _format_inline_markdown(blockquote_match.group(1).strip())
            rendered_lines.append(f"> {content}")
            previous_blank = False
            continue

        rendered_lines.append(_format_inline_markdown(line))
        previous_blank = False

    return "\n".join(rendered_lines).strip("\n")


def consume_pending_changelog() -> tuple[str, str] | None:
    try:
        tag = PENDING_CHANGELOG_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if not tag:
        try:
            PENDING_CHANGELOG_PATH.unlink()
        except OSError:
            pass
        return None
    content = get_changelog_for_version(tag)
    if content is None:
        return None
    try:
        PENDING_CHANGELOG_PATH.unlink()
    except OSError:
        pass
    return tag, content


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

    changelog_text = fetch_and_cache_changelog(latest_version, force_refresh=True)
    set_pending_changelog(latest_version)
    if changelog_text:
        print(
            f"{Colors.YELLOW}Release notes cached. They will be shown on next launch "
            f"or via 'ashell changelog'.{Colors.RESET}"
        )
    else:
        print(
            f"{Colors.YELLOW}Tip:{Colors.RESET} Run 'ashell changelog' after restarting to check the latest changes."
        )

    print(
        f"{Colors.GREEN}{Colors.BOLD}Upgrade complete.{Colors.RESET} "
        f"Restart AShell to use {display_latest} (reload -full)."
    )
    return 0


__all__ = [
    "check_for_newer_version",
    "fetch_latest_release_info",
    "format_version_for_display",
    "get_cached_changelog",
    "get_changelog_for_version",
    "fetch_and_cache_changelog",
    "set_pending_changelog",
    "consume_pending_changelog",
    "render_markdown_for_terminal",
    "perform_upgrade",
]
