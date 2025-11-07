from __future__ import annotations

import json
from pathlib import Path
try:
    import readline
except Exception:
    try:
        import pyreadline3 as readline
    except Exception:
        readline = None
import shlex
import subprocess
import platform
import psutil
import os
import socket
import sys
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime

from commands import commandHelper
from autocomplete import (
    completer,
    resolve_external_executable,
    set_current_working_folder,
)


SHELL_VERSION = "0.1.1"
CONFIG_DIR = Path.home() / ".ashell"
CONFIG_PATH = CONFIG_DIR / ".ashell.conf"
START_DIR_ENV = "ASHELL_START_DIR"

DEFAULT_CONFIG: dict[str, object] = {
    "show_welcome_screen": True,
    "prompt": {
        "show_user_host": True,
        "show_time": True,
        "show_path": True,
        "show_symbol": True,
        "symbol": "$",
    },
}


REPO_OWNER = "DuperKnight"
REPO_NAME = "AShell"
TAGS_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/tags"

_LATEST_RELEASE_CACHE: tuple[str, str] | None = None


if platform.system() == "Windows":
    try:
        import colorama

        try:
            colorama.just_fix_windows_console()
        except AttributeError:
            colorama.init()
    except Exception:
        pass


def _default_config_copy() -> dict[str, object]:
    return json.loads(json.dumps(DEFAULT_CONFIG))


def _mark_ansi_sequences(value: str) -> str:
    if "\033" not in value:
        return value

    pieces: list[str] = []
    idx = 0
    length = len(value)
    while idx < length:
        ch = value[idx]
        if ch == "\033":
            end = idx + 1
            while end < length and value[end] != "m":
                end += 1
            if end < length:
                end += 1
                pieces.append("\001")
                pieces.append(value[idx:end])
                pieces.append("\002")
                idx = end
                continue
        pieces.append(ch)
        idx += 1

    return "".join(pieces)


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


def _format_version_for_display(version: str) -> str:
    stripped = version.strip()
    if stripped.lower().startswith("v"):
        return stripped
    return f"v{stripped}"


def _fetch_latest_release_info(force_refresh: bool = False) -> tuple[str, str] | None:
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


def _check_for_update_notice(force_refresh: bool = False) -> str | None:
    release = _fetch_latest_release_info(force_refresh=force_refresh)
    if not release:
        return None
    latest_version, _ = release
    try:
        if _compare_versions(latest_version, SHELL_VERSION) <= 0:
            return None
    except ValueError:
        return None

    display_latest = _format_version_for_display(latest_version)
    display_current = _format_version_for_display(SHELL_VERSION)
    return (
        f"{bcolors.WARNING}AShell update available: {display_latest} "
        f"(current {display_current}). Run 'ashell upgrade' to install.{bcolors.ENDC}"
    )


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


def _perform_upgrade() -> int:
    print(f"{bcolors.BOLD}Checking for updates...{bcolors.ENDC}")
    release = _fetch_latest_release_info(force_refresh=True)
    if not release:
        print("AShell: Could not retrieve release information from GitHub.")
        return 1

    latest_version, zip_url = release
    try:
        comparison = _compare_versions(latest_version, SHELL_VERSION)
    except ValueError:
        print("AShell: Unable to compare version numbers.")
        return 1

    if comparison <= 0:
        print("AShell is already up to date.")
        return 0

    display_latest = _format_version_for_display(latest_version)
    display_current = _format_version_for_display(SHELL_VERSION)
    print(f"Upgrading AShell from {display_current} to {display_latest}...")

    install_dir = Path(__file__).resolve().parent
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            archive_path = tmp_path / "ashell.zip"
            _download_release_archive(zip_url, archive_path)
            extracted_root = _extract_release_archive(archive_path, tmp_path / "src")
            _copy_release_contents(extracted_root, install_dir)
    except (urllib.error.URLError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"AShell: Upgrade failed: {exc}")
        return 1

    if not _install_requirements(install_dir):
        return 1

    print(f"{bcolors.GREEN}{bcolors.BOLD}Upgrade complete.{bcolors.ENDC} Restart AShell to use {display_latest}.")
    return 0


def load_config() -> dict[str, object]:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            return loaded
        raise ValueError("Configuration root must be an object")
    except FileNotFoundError:
        config = _default_config_copy()
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with CONFIG_PATH.open("w", encoding="utf-8") as handle:
                json.dump(config, handle, indent=2)
        except OSError as exc:
            print(f"AShell: Could not write default config ({CONFIG_PATH}): {exc}")
        return config
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"AShell: Failed to parse config ({CONFIG_PATH}): {exc}")
    except OSError as exc:
        print(f"AShell: Could not read config ({CONFIG_PATH}): {exc}")
    return _default_config_copy()


def _format_prompt_path(path: Path) -> str:
    home = Path.home()
    try:
        resolved_path = path.expanduser().resolve()
    except OSError:
        resolved_path = path

    try:
        rel = resolved_path.relative_to(home)
        if str(rel) == ".":
            return "~"
        return str(Path("~") / rel)
    except ValueError:
        return str(resolved_path)


def _build_prompt(working_folder: Path, config: dict[str, object]) -> str:
    try:
        user = os.getlogin()
    except OSError:
        user = os.environ.get("USER", "user")
    host = socket.gethostname().split(".")[0]
    clock = datetime.now().strftime("%H:%M:%S")
    path_display = _format_prompt_path(working_folder)
    prompt_section = config.get("prompt", {})
    if not isinstance(prompt_section, dict):
        prompt_section = {}

    show_user_host = prompt_section.get("show_user_host", True)
    show_time = prompt_section.get("show_time", True)
    show_path = prompt_section.get("show_path", True)
    show_symbol = prompt_section.get("show_symbol", True)
    symbol = prompt_section.get("symbol", "$")

    if not isinstance(symbol, str) or not symbol:
        symbol = "$"

    prompt_parts: list[str] = []
    if bool(show_user_host):
        prompt_parts.append(
            f"{bcolors.BOLD}{user}{bcolors.ENDC}@{bcolors.BLUE}{host}{bcolors.ENDC}"
        )
    if bool(show_time):
        prompt_parts.append(f"{bcolors.DIM}{clock}{bcolors.ENDC}")
    if bool(show_path):
        prompt_parts.append(f"{bcolors.GREEN}{path_display}{bcolors.ENDC}")

    suffix = f"{bcolors.BOLD}{symbol}{bcolors.ENDC}" if bool(show_symbol) else ""
    body = " ".join(part for part in prompt_parts if part)

    if body and suffix:
        prompt_text = f"{body} {suffix} "
    elif body:
        prompt_text = f"{body} "
    elif suffix:
        prompt_text = f"{suffix} "
    else:
        prompt_text = "> "

    return _mark_ansi_sequences(prompt_text) if readline else prompt_text


def _clear_screen(working_folder: Path) -> None:
    commandHelper.run(str(working_folder), "clear")


def _render_welcome_screen() -> None:
    logo_lines = f"""   █████████  
  ███▒▒▒▒▒███ 
 ▒███    ▒███ 
 ▒███████████ 
 ▒███▒▒▒▒▒███ 
 ▒███    ▒███ 
 █████   █████
▒▒▒▒▒   ▒▒▒▒▒ {bcolors.ENDC}""".splitlines()

    info_lines = get_system_info()

    for i in range(max(len(logo_lines), len(info_lines))):
        logo_line = logo_lines[i] if i < len(logo_lines) else " " * 12
        info_line = info_lines[i] if i < len(info_lines) else ""
        print(f"{logo_line}  {info_line}")

    print("\n" + "┌──────────────────────────────────────────┐")
    print(f"│ {bcolors.BOLD}Welcome to AShell!{bcolors.ENDC}                       │")
    print(f"│ Type {bcolors.GREEN}'help'{bcolors.ENDC} for a list of commands.      │")
    print(f"│ Type {bcolors.GREEN}'exit'{bcolors.ENDC} to quit.                     │")
    print("└──────────────────────────────────────────┘\n")


def _run_external_command(working_folder: Path | str, command: str, args: list[str]) -> None:
    working_dir = str(working_folder)
    executable = resolve_external_executable(command, working_dir)
    if not executable:
        print(f"AShell: command not found: {command}")
        return

    try:
        completed = subprocess.run([executable, *args], cwd=working_dir)
        if completed.returncode not in (0, None):
            print(f"Process exited with status {completed.returncode}")
    except PermissionError:
        print(f"AShell: permission denied: {command}")
    except FileNotFoundError:
        print(f"AShell: command not found after resolution: {command}")
    except OSError as exc:
        print(f"AShell: failed to execute '{command}': {exc}")


def get_system_info():
    try:
        try:
            user = os.getlogin()
        except OSError:
            user = os.environ.get("USER", "unknown")
        hostname = socket.gethostname()
        
        os_info = f"{platform.system()} {platform.release()}"

        boot_time_timestamp = psutil.boot_time()
        uptime_seconds = datetime.now().timestamp() - boot_time_timestamp
        days = int(uptime_seconds // (24 * 3600))
        hours = int((uptime_seconds % (24 * 3600)) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        uptime_str = f"{days}d {hours}h {minutes}m"

        cpu_info = platform.processor() or platform.uname().processor

        if not cpu_info:
            try:
                cpu_info = psutil.cpu_info().brand_raw
            except (AttributeError, Exception):
                cpu_info = ""

        if not cpu_info:
            try:
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as cpuinfo:
                    for line in cpuinfo:
                        if line.startswith("model name"):
                            cpu_info = line.split(":", 1)[1].strip()
                            if cpu_info:
                                break
            except OSError:
                cpu_info = ""

        if not cpu_info:
            cpu_info = platform.machine() or "Unknown CPU"

        mem = psutil.virtual_memory()
        mem_total_gb = mem.total / (1024**3)
        mem_used_gb = mem.used / (1024**3)
        mem_percent = mem.percent
        mem_info = f"{mem_used_gb:.1f}GiB / {mem_total_gb:.1f}GiB ({mem_percent}%)"

        return [
            f"{bcolors.BOLD}{user}@{hostname}{bcolors.ENDC}",
            "-----------------",
            f"{bcolors.BOLD}OS{bcolors.ENDC}: {os_info}",
            f"{bcolors.BOLD}Uptime{bcolors.ENDC}: {uptime_str}",
            f"{bcolors.BOLD}CPU{bcolors.ENDC}: {cpu_info}",
            f"{bcolors.BOLD}Shell{bcolors.ENDC}: AShell v{SHELL_VERSION}",
            f"{bcolors.BOLD}Memory{bcolors.ENDC}: {mem_info}",
        ]
    except Exception as e:
        return [f"Could not fetch system info: {e}"]


def main():
    config = load_config()
    update_notice_message = _check_for_update_notice()

    start_dir = os.environ.pop(START_DIR_ENV, "")
    if start_dir:
        candidate = Path(start_dir)
        try:
            if candidate.exists() and candidate.is_dir():
                working_folder = candidate
            else:
                working_folder = Path.home()
        except OSError:
            working_folder = Path.home()
    else:
        working_folder = Path.home()
    set_current_working_folder(str(working_folder))

    if readline:
        readline.set_completer(completer)
        readline.set_completer_delims(" \t\n")
        try:
            readline.parse_and_bind("tab: complete")
            readline.parse_and_bind("set show-all-if-ambiguous on")
        except Exception:
            # Some readline implementations don't support these options
            pass

    _clear_screen(working_folder)

    if bool(config.get("show_welcome_screen", True)):
        _render_welcome_screen()
    if update_notice_message:
        print(update_notice_message)

    while True:
        prompt = _build_prompt(working_folder, config)
        command = input(prompt)
        command_stripped = command.strip()
        if not command_stripped:
            continue
        command_lower = command_stripped.lower()

        if command_lower == 'exit':
            print("Exiting AShell. Goodbye!")
            break

        elif command_lower == 'reload' or command_lower.startswith('reload '):
            try:
                reload_tokens = shlex.split(command)
            except ValueError:
                print("AShell: Failed to parse reload arguments")
                continue

            flags = reload_tokens[1:]
            full_flags = {"--full", "--hard", "--all", "-f", "-a"}
            full_reload = any(flag in full_flags for flag in flags)
            unknown_flags = [flag for flag in flags if flag not in full_flags]

            if unknown_flags:
                print(
                    "AShell: Unknown reload flag(s): "
                    + ", ".join(unknown_flags)
                )
                continue

            if full_reload:
                print(f"{bcolors.DIM}Performing full reload...{bcolors.ENDC}")
                os.environ[START_DIR_ENV] = str(working_folder)
                try:
                    os.execl(sys.executable, sys.executable, *sys.argv)
                except OSError as exc:
                    print(f"AShell: Failed to fully reload: {exc}")
                    os.environ.pop(START_DIR_ENV, None)
                continue

            print(f"{bcolors.DIM}Reloading AShell...{bcolors.ENDC}")
            config = load_config()
            update_notice_message = _check_for_update_notice(force_refresh=True)
            set_current_working_folder(str(working_folder))
            _clear_screen(working_folder)
            if bool(config.get("show_welcome_screen", True)):
                _render_welcome_screen()
            if update_notice_message:
                print(update_notice_message)
            continue

        elif command_lower == 'help':
            print(                    "- Available commands:")
            print(                    "  | help - Show this help message")
            print(bcolors.CHILL_DIM + "  | cd - Go to a folder" + bcolors.ENDC)
            print(                    "  | ls - Check whats inside a folder")
            print(bcolors.CHILL_DIM + "  | clear - Clears the shell" + bcolors.ENDC)
            print(                    "  | mkdir - Creates a directory in a desired folder")
            print(bcolors.CHILL_DIM + "  | touch - Creates an empty file" + bcolors.ENDC)
            print(                    "  | rm - Deletes a file/folder")
            print(bcolors.CHILL_DIM + "  | micro - Edit any file" + bcolors.ENDC)
            print(                    "  | reload [--full] - Reload AShell")
            print(bcolors.CHILL_DIM + "  | exit - Exit the shell" + bcolors.ENDC)

        elif command_lower == 'info':
            info = get_system_info()
            print("\n".join(info))

        else:
            try:
                parts = shlex.split(command)
            except ValueError:
                print("AShell: Failed to parse command input")
                continue

            if len(parts) == 0:
                continue

            cmd = parts[0]
            args = parts[1:]

            handled, folder = commandHelper.run(working_folder, cmd, *args)
            if handled:
                if folder:
                    new_folder = Path(folder)
                    if new_folder != working_folder:
                        working_folder = new_folder
                        set_current_working_folder(str(working_folder))
                continue

            _run_external_command(working_folder, cmd, args)


class bcolors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    CHILL_DIM = "\033[37m"
    DIM = '\033[2m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


if __name__ == "__main__":
    cli_args = sys.argv[1:]
    if cli_args:
        primary = cli_args[0].lower()
        if primary == "upgrade":
            if len(cli_args) > 1:
                print("AShell: 'upgrade' does not accept additional arguments.")
                sys.exit(1)
            sys.exit(_perform_upgrade())
        print(f"AShell: unknown argument '{cli_args[0]}'")
        sys.exit(1)
    main()