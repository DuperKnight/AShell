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

cleanup() {
    rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

log() {
    printf "%s\n" "$*"
}

error() {
    printf "Error: %s\n" "$*" >&2
    exit 1
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

    local api_url="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"
    log "Fetching latest release metadata..."

    local asset_url
    asset_url="$(${PYTHON} <<'PY'
import json
import sys
import urllib.request

api_url = sys.argv[1]
with urllib.request.urlopen(api_url) as resp:
    data = json.load(resp)

asset_url = None
for asset in data.get("assets", []):
    name = asset.get("name", "")
    if name.endswith(".zip"):
        asset_url = asset.get("browser_download_url")
        break

if not asset_url:
    asset_url = data.get("zipball_url")

if asset_url:
    print(asset_url)
PY
"${api_url}")"

    if [ -z "${asset_url}" ]; then
        error "Could not find a downloadable asset for the latest release."
    fi

    log "Downloading latest release from ${asset_url}"
    curl -fsSL "${asset_url}" -o "${TMP_DIR}/ashell.zip"
}

extract_release() {
    log "Extracting release archive..."

    local extracted_dir
    extracted_dir="$(${PYTHON} <<'PY' "${TMP_DIR}/ashell.zip" "${TMP_DIR}/src"
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
    "${PYTHON}" <<'PY' "${extracted_dir}" "${INSTALL_DIR}"
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
    local config_action
    config_action="$(${PYTHON} <<'PY' "${INSTALL_DIR}" "${CONFIG_HOME}" "${CONFIG_FILE}")"
import json
import pathlib
import sys
import importlib.util

install_dir = pathlib.Path(sys.argv[1])
config_home = pathlib.Path(sys.argv[2])
config_path = pathlib.Path(sys.argv[3])

config_home.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("ashell_install_shell", install_dir / "shell.py")
module = importlib.util.module_from_spec(spec)
if not spec.loader:
    raise RuntimeError("Unable to load shell module for configuration setup")
spec.loader.exec_module(module)

default_config = getattr(module, "DEFAULT_CONFIG", {}) or {}
write_status = sys.stdout.write

def write_default():
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(default_config, handle, indent=2)

if not config_path.exists():
    write_default()
    write_status("created")
else:
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if not isinstance(existing, dict):
            raise ValueError("Configuration root must be an object")
        write_status("kept")
    except Exception:
        backup_path = config_path.with_suffix(config_path.suffix + ".bak")
        try:
            config_path.replace(backup_path)
        except Exception:
            pass
        write_default()
        write_status(f"reset:{backup_path}")
PY
    case "${config_action}" in
        created)
            log "Configuration created at ${CONFIG_FILE}"
            ;;
        kept)
            log "Existing configuration preserved at ${CONFIG_FILE}"
            ;;
        reset:*)
            local backup_path="${config_action#reset:}"
            log "Existing configuration was invalid; backup saved to ${backup_path} and defaults restored."
            ;;
        *)
            log "Configuration stored at ${CONFIG_FILE}"
            ;;
    esac
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
    detect_python
    print_banner
    fetch_latest_release
    extract_release
    setup_venv
    setup_configuration
    create_wrapper
    ensure_path_export
    log "AShell installed successfully. Restart your terminal or source your shell profile, then run 'ashell' to start."
    log "Customize your shell via ${CONFIG_FILE}."
}

main "$@"
