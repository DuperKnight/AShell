#!/usr/bin/env bash

set -euo pipefail

REPO_OWNER="DuperKnight"
REPO_NAME="AShell"
INSTALL_DIR="${HOME}/.local/share/ashell"
BIN_DIR="${HOME}/.local/bin"
WRAPPER_PATH="${BIN_DIR}/ashell"
TMP_DIR="$(mktemp -d)"
CONFIG_HOME="${HOME}/.ashell"
CONFIG_FILE="${CONFIG_HOME}/.ashell.conf"

COLOR_RESET='\033[0m'
COLOR_BOLD='\033[1m'
COLOR_DIM='\033[2m'
COLOR_MAGENTA='\033[35m'
COLOR_CYAN='\033[36m'
COLOR_GREEN='\033[32m'
COLOR_RED='\033[31m'

cleanup() {
    rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

log() {
    local message="$*"
    printf "%b-%b %b\n" "${COLOR_MAGENTA}" "${COLOR_RESET}" "${message}"
}

error() {
    local message="$*"
    printf "%b[ERR]%b %b\n" "${COLOR_RED}${COLOR_BOLD}" "${COLOR_RESET}" "${message}" >&2
    exit 1
}

section() {
    local text="$*"
    local styled="${COLOR_BOLD}${COLOR_CYAN}${text}${COLOR_RESET}"
    printf "\n%b==>%b %b\n" "${COLOR_DIM}" "${COLOR_RESET}" "${styled}"
}

success() {
    local message="$*"
    printf "%b[OK]%b %b\n" "${COLOR_GREEN}${COLOR_BOLD}" "${COLOR_RESET}" "${message}"
}

ACTION="${ASHELL_ACTION:-}"

usage() {
    cat <<'EOF'
Usage: install.sh [--reinstall|-r] [--delete|-d] [--abort|-a] [--help|-h]

When piping via curl, pass flags after "bash -s --" e.g.:
  curl -fsSL https://raw.githubusercontent.com/DuperKnight/AShell/main/install.sh | bash -s -- --reinstall

Environment alternative:
  ASHELL_ACTION=reinstall|delete|abort curl -fsSL ... | bash -s --
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --reinstall|-r)
                ACTION="reinstall";
                ;;
            --delete|-d)
                ACTION="delete";
                ;;
            --abort|-a)
                ACTION="abort";
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                error "Unknown argument: $1 (use --help)"
                ;;
        esac
        shift
    done
}

prompt_action_interactive() {
    local prompt_msg="Choose an action: [R]einstall, [D]elete, [A]bort: "
    local choice=""
    if [ -t 0 ]; then
        printf "%s" "${prompt_msg}"
        
        read -r choice || true
    elif [ -r /dev/tty ]; then
        
        printf "%s" "${prompt_msg}" > /dev/tty
        
        read -r choice < /dev/tty || true
    else
        
        error "No TTY available to prompt for action. Re-run with --reinstall/--delete flags or set ASHELL_ACTION."
    fi

    case "${choice}" in
        [Rr]) ACTION="reinstall" ;;
        [Dd]) ACTION="delete" ;;
        [Aa]|"" ) ACTION="abort" ;;
        *) ACTION="abort" ;;
    esac
}

ensure_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        error "$1 is required but not installed."
    fi
}

print_banner() {
    printf '\033[1;35m'
    cat <<'EOF'
   █████████    █████████  █████               ████  ████ 
  ███▒▒▒▒▒███  ███▒▒▒▒▒███▒▒███               ▒▒███ ▒▒███ 
 ▒███    ▒███ ▒███    ▒▒▒  ▒███████    ██████  ▒███  ▒███ 
 ▒███████████ ▒▒█████████  ▒███▒▒███  ███▒▒███ ▒███  ▒███ 
 ▒███▒▒▒▒▒███  ▒▒▒▒▒▒▒▒███ ▒███ ▒███ ▒███████  ▒███  ▒███ 
 ▒███    ▒███  ███    ▒███ ▒███ ▒███ ▒███▒▒▒   ▒███  ▒███ 
 █████   █████▒▒█████████  ████ █████▒▒██████  █████ █████
▒▒▒▒▒   ▒▒▒▒▒  ▒▒▒▒▒▒▒▒▒  ▒▒▒▒ ▒▒▒▒▒  ▒▒▒▒▒▒  ▒▒▒▒▒ ▒▒▒▒▒ 
                                                         
                                                         
                                                         
EOF
    printf '\033[0m'
    printf '\033[1;36m           Welcome to the AShell installer!\033[0m\n'
    printf '\033[2m------------------------------------------------------------\033[0m\n\n'
}

detect_python() {
    if command -v python3 >/dev/null 2>&1; then
        PYTHON="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON="python"
    else
        error "Python 3 is required but was not found."
    fi

    local version
    version="$(${PYTHON} -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    local major minor
    major="${version%%.*}"
    minor="${version#*.}"; minor="${minor%%.*}"

    if [ "${major}" -lt 3 ] || { [ "${major}" -eq 3 ] && [ "${minor}" -lt 8 ]; }; then
        error "Python 3.8 or newer is required. Current version: ${version}."
    fi
}

fetch_latest_release() {
    ensure_command curl

    local api_url="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/tags"
    log "Fetching latest tag metadata..."

    local asset_url
    asset_url="$(${PYTHON} - "${api_url}" <<'PY'
import json
import sys
import urllib.request
from urllib.error import HTTPError

api_url = sys.argv[1]
headers = {"User-Agent": "AShell-Installer"}
request = urllib.request.Request(api_url, headers=headers)

try:
    with urllib.request.urlopen(request, timeout=30) as resp:
        data = json.load(resp)
except HTTPError as exc:
    if exc.code == 404:
        print("", end="")
        sys.exit(0)
    raise

if not isinstance(data, list):
    print("", end="")
    sys.exit(0)

def parse_version(name: str):
    parts = name.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return None

best = None
for entry in data:
    tag_name = entry.get("name", "")
    version = parse_version(tag_name)
    zip_url = entry.get("zipball_url")
    if version is None or not zip_url:
        continue
    if best is None or version > best[0]:
        best = (version, zip_url)

if best:
    print(best[1])
PY
)"

    if [ -z "${asset_url}" ]; then
        error "Could not determine a downloadable zip from tags. Ensure tags follow 'major.minor.patch' and are available."
    fi

    log "Downloading latest tagged source from ${asset_url}"
    curl -fsSL "${asset_url}" -o "${TMP_DIR}/ashell.zip"
}

extract_release() {
    log "Extracting release archive..."

    local extracted_dir
    extracted_dir="$(${PYTHON} - "${TMP_DIR}/ashell.zip" "${TMP_DIR}/src" <<'PY'
import os
import sys
import zipfile

zip_path, dest_dir = sys.argv[1:3]
os.makedirs(dest_dir, exist_ok=True)

with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(dest_dir)
    top_level = None
    for member in zf.namelist():
        parts = member.split('/', 1)
        if parts and parts[0] and not parts[0].startswith('__MACOSX'):
            top_level = parts[0]
            break

if not top_level:
    sys.exit(1)

print(os.path.join(dest_dir, top_level))
PY
)"
    if [ -z "${extracted_dir}" ]; then
        error "Failed to locate extracted source directory."
    fi

    rm -rf "${INSTALL_DIR}"
    mkdir -p "${INSTALL_DIR}"
    "${PYTHON}" - "${extracted_dir}" "${INSTALL_DIR}" <<'PY'
import os
import shutil
import sys

src, dest = sys.argv[1:3]

for entry in os.listdir(src):
    shutil.copytree(
        os.path.join(src, entry),
        os.path.join(dest, entry),
        dirs_exist_ok=True,
    ) if os.path.isdir(os.path.join(src, entry)) else shutil.copy2(
        os.path.join(src, entry),
        os.path.join(dest, entry)
    )
PY
}

setup_venv() {
    log "Creating virtual environment..."
    "${PYTHON}" -m venv "${INSTALL_DIR}/.venv"

    log "Installing dependencies..."
    "${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip >/dev/null
    if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
        "${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
    else
        log "No requirements.txt found; skipping dependency installation."
    fi
}

setup_configuration() {
    log "Preparing configuration..."
    local venv_python="${INSTALL_DIR}/.venv/bin/python"
    if [ ! -x "${venv_python}" ]; then
        error "Virtual environment interpreter not found at ${venv_python}"
    fi

    if [ -n "${REINSTALL_MODE:-}" ]; then
        log "Reinstall mode enabled; resetting configuration."
        rm -f "${CONFIG_FILE}"
    elif [ -f "${CONFIG_FILE}" ]; then
        log "Existing configuration detected at ${CONFIG_FILE}; skipping initialization."
        return
    fi

    local tmp_config_script
    tmp_config_script="$(mktemp)"

    cat <<'PY' > "${tmp_config_script}"
import json
import os
import pathlib
import sys
import importlib.util

def obtain_paths():
    if len(sys.argv) >= 4:
        return map(pathlib.Path, sys.argv[1:4])
    env = os.environ
    return (
        pathlib.Path(env["ASHELL_INSTALL_DIR"]),
        pathlib.Path(env["ASHELL_CONFIG_HOME"]),
        pathlib.Path(env["ASHELL_CONFIG_FILE"]),
    )

install_dir, config_home, config_path = obtain_paths()
config_home.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("ashell_install_shell", install_dir / "shell.py")
module = importlib.util.module_from_spec(spec)
if not spec.loader:
    raise RuntimeError("Unable to load shell module for configuration setup")
spec.loader.exec_module(module)

default_config = getattr(module, "DEFAULT_CONFIG", {}) or {}
config = json.loads(json.dumps(default_config))
prompt_config = config.get("prompt", {})

def ask_bool(question: str, default: bool) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        try:
            answer = input(f"{question}{suffix} ").strip().lower()
        except EOFError:
            return default
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer 'y' or 'n'.")

def ask_text(question: str, default: str) -> str:
    prompt = f"{question} [{default}]: "
    try:
        response = input(prompt)
    except EOFError:
        return default
    response = response.strip()
    return response or default

print("\n--- AShell Configuration Setup ---")

config["show_welcome_screen"] = ask_bool(
    "Show welcome screen?", bool(config.get("show_welcome_screen", True))
)

prompt_config["show_user_host"] = ask_bool(
    "Show user@host in prompt?", bool(prompt_config.get("show_user_host", True))
)

prompt_config["show_time"] = ask_bool(
    "Show time in prompt?", bool(prompt_config.get("show_time", True))
)

prompt_config["show_path"] = ask_bool(
    "Show path in prompt?", bool(prompt_config.get("show_path", True))
)

prompt_config["show_symbol"] = ask_bool(
    "Show prompt symbol?", bool(prompt_config.get("show_symbol", True))
)

prompt_config["symbol"] = ask_text(
    "Prompt symbol", str(prompt_config.get("symbol", "$")) or "$"
)

config["prompt"] = prompt_config

with config_path.open("w", encoding="utf-8") as handle:
    json.dump(config, handle, indent=2)

print(f"\nConfiguration written to {config_path}\n")
PY

    ASHELL_INSTALL_DIR="${INSTALL_DIR}" \
    ASHELL_CONFIG_HOME="${CONFIG_HOME}" \
    ASHELL_CONFIG_FILE="${CONFIG_FILE}" \
    PYTHONPATH="${INSTALL_DIR}${PYTHONPATH:+:${PYTHONPATH}}" \
        "${venv_python}" "${tmp_config_script}"
    rm -f "${tmp_config_script}"

    log "Configuration saved to ${CONFIG_FILE}"
}

create_wrapper() {
    mkdir -p "${BIN_DIR}"
    cat > "${WRAPPER_PATH}" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/.venv/bin/python" "${INSTALL_DIR}/shell.py" "\$@"
EOF
    chmod +x "${WRAPPER_PATH}"
}

ensure_path_export() {
    case "${SHELL##*/}" in
        zsh)
            PROFILE_FILE="${HOME}/.zshrc"
            ;;
        fish)
            PROFILE_FILE="${HOME}/.config/fish/config.fish"
            ;;
        *)
            PROFILE_FILE="${HOME}/.bashrc"
            ;;
    esac

    if ! printf '%s' "${PATH}" | tr ':' '\n' | grep -qx "${BIN_DIR}"; then
        log "Adding ${BIN_DIR} to PATH in ${PROFILE_FILE}"
        mkdir -p "$(dirname "${PROFILE_FILE}")"
        if [ "${PROFILE_FILE##*.}" = "fish" ]; then
            if ! grep -Fq "set -gx PATH ${BIN_DIR}" "${PROFILE_FILE}" 2>/dev/null; then
                printf '\nset -gx PATH %s $PATH\n' "${BIN_DIR}" >> "${PROFILE_FILE}"
            fi
        else
            if ! grep -Fq "${BIN_DIR}" "${PROFILE_FILE}" 2>/dev/null; then
                printf '\nexport PATH="%s:$PATH"\n' "${BIN_DIR}" >> "${PROFILE_FILE}"
            fi
        fi
    fi
}

main() {
    parse_args "$@"
    if [ -d "${INSTALL_DIR}" ]; then
        printf "AShell is already installed at %s.\n" "${INSTALL_DIR}"
        
        if [ -z "${ACTION}" ]; then
            prompt_action_interactive
        fi
        case "${ACTION}" in
            reinstall)
                log "Reinstall selected; configuration will be reset."
                REINSTALL_MODE=1
                ;;
            delete)
                log "Delete selected; removing existing installation."
                rm -rf "${INSTALL_DIR}"
                rm -f "${WRAPPER_PATH}"
                if [ -f "${CONFIG_FILE}" ]; then
                    rm -f "${CONFIG_FILE}"
                fi
                log "AShell installation removed."
                exit 0
                ;;
            abort|*)
                log "Installation aborted. Use --reinstall/--delete to override."
                exit 0
                ;;
        esac
    fi

    detect_python
    printf '\033c'
    print_banner

    section "Download"
    fetch_latest_release

    section "Extract"
    extract_release

    section "Virtual Environment"
    setup_venv

    section "Configuration"
    setup_configuration

    section "Final Touches"
    create_wrapper
    ensure_path_export

    success "AShell installed successfully."
    log "Restart your terminal or source your shell profile, then run ${COLOR_BOLD}ashell${COLOR_RESET}."
    log "Customize your shell via ${COLOR_BOLD}${CONFIG_FILE}${COLOR_RESET}."
}

main "$@"
