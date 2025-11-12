import os
import subprocess
import sys
from pathlib import Path

from upgrade import (
    format_version_for_display,
    get_changelog_for_version,
    render_markdown_for_terminal,
)

aliases = ["ashell"]
num_arguments = 32

_SHELL_SCRIPT = Path(__file__).resolve().parent.parent / "shell.py"


def _run_shell_process(*cli_args: str) -> subprocess.CompletedProcess[int]:
    command = [sys.executable, str(_SHELL_SCRIPT), *cli_args]
    return subprocess.run(command, env=os.environ.copy())


def _print_version() -> None:
    display = os.environ.get("ASHELL_DISPLAY_NAME")
    if not display:
        name = os.environ.get("ASHELL_NAME", "AShell")
        version = os.environ.get("ASHELL_VERSION")
        if version:
            display = f"{name} v{version}" if not version.startswith("v") else f"{name} {version}"
        else:
            display = name
    print(display)


def run(working_folder, *args):
    if not args:
        _print_version()
        print("Usage: ashell [version|--version|-version|-v|-c <command>|upgrade|changelog [version]]")
        return

    option = args[0]
    option_lower = option.lower()

    if option_lower in {"version", "--version", "-version", "-v"}:
        if len(args) > 1:
            print("ashell: version commands do not accept additional arguments.")
            return

        canonical_flag = "version" if option_lower == "version" else option_lower
        result = _run_shell_process(canonical_flag)
        if result.returncode != 0:
            print(f"ashell: version command failed with status {result.returncode}.")
        return

    if option_lower == "upgrade":
        if len(args) > 1:
            print("ashell: 'upgrade' does not accept additional arguments.")
            return

        result = _run_shell_process("upgrade")
        if result.returncode != 0:
            print(f"ashell: upgrade failed with status {result.returncode}.")
        return

    if option_lower == "changelog":
        if len(args) > 2:
            print("ashell: 'changelog' accepts at most one version argument.")
            return

        version = args[1] if len(args) == 2 else os.environ.get("ASHELL_VERSION")
        if not version:
            print("ashell: Unable to determine AShell version.")
            return

        changelog = get_changelog_for_version(version)
        if not changelog:
            display_version = format_version_for_display(version)
            print(f"ashell: Unable to load changelog for {display_version}.")
            return

        display_version = format_version_for_display(version)
        print(f"=== AShell {display_version} Changelog ===")
        rendered = render_markdown_for_terminal(changelog)
        print(rendered if rendered else changelog.strip())
        print()
        return

    if option_lower == "-c":
        if len(args) < 2:
            print("ashell: '-c' requires a command string.")
            return

        command_string = " ".join(args[1:])
        result = _run_shell_process("-c", command_string)
        if result.returncode != 0:
            print(f"ashell: '-c' command exited with status {result.returncode}.")
        return

    print(f"ashell: unknown subcommand '{option}'.")
