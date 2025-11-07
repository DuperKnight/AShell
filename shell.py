from __future__ import annotations

import json
from pathlib import Path
try:
    import readline  # type: ignore
except Exception:
    try:
        import pyreadline3 as readline  # type: ignore
    except Exception:
        readline = None  # type: ignore
import shlex
import subprocess
import platform
import psutil
import os
import socket
import sys
from datetime import datetime

from commands import commandHelper
from autocomplete import (
    completer,
    resolve_external_executable,
    set_current_working_folder,
)


SHELL_VERSION = "0.1.0"
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


# On Windows, ensure ANSI colors work in most consoles
if platform.system() == "Windows":
    try:
        import colorama  # type: ignore

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
            set_current_working_folder(str(working_folder))
            _clear_screen(working_folder)
            if bool(config.get("show_welcome_screen", True)):
                _render_welcome_screen()
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
    main()