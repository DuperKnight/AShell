#Requires -Version 5.1

param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "AShell"),
    [string]$ReleaseApi = "https://api.github.com/repos/DuperKnight/AShell/tags"
)

$ConfigDir = Join-Path $env:USERPROFILE '.ashell'
$ConfigFile = Join-Path $ConfigDir '.ashell.conf'

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ColorReset    = "`e[0m"
$ColorBold     = "`e[1m"
$ColorDim      = "`e[2m"
$ColorMagenta  = "`e[35m"
$ColorCyan     = "`e[36m"
$ColorGreen    = "`e[32m"
$ColorRed      = "`e[31m"

function Write-Log {
    param([string]$Message)
    Write-Host "$ColorMagenta-$ColorReset $Message"
}

function Throw-Error {
    param([string]$Message)
    throw "$ColorRed$ColorBold[ERR]$ColorReset $Message"
}

function Write-Section {
    param([string]$Message)
    Write-Host "" # spacer
    Write-Host "$ColorDim==>$ColorReset $ColorBold$ColorCyan$Message$ColorReset"
}

function Write-Success {
    param([string]$Message)
    Write-Host "$ColorGreen$ColorBold[OK]$ColorReset $Message"
}

function Show-Banner {
    Write-Host ''
    Write-Host "${ColorMagenta}   █████████    █████████  █████               ████  ████ ${ColorReset}"
    Write-Host "${ColorMagenta}  ███▒▒▒▒▒███  ███▒▒▒▒▒███▒▒███               ▒▒███ ▒▒███ ${ColorReset}"
    Write-Host "${ColorMagenta} ▒███    ▒███ ▒███    ▒▒▒  ▒███████    ██████  ▒███  ▒███ ${ColorReset}"
    Write-Host "${ColorMagenta} ▒███████████ ▒▒█████████  ▒███▒▒███  ███▒▒███ ▒███  ▒███ ${ColorReset}"
    Write-Host "${ColorMagenta} ▒███▒▒▒▒▒███  ▒▒▒▒▒▒▒▒███ ▒███ ▒███ ▒███████  ▒███  ▒███ ${ColorReset}"
    Write-Host "${ColorMagenta} ▒███    ▒███  ███    ▒███ ▒███ ▒███ ▒███▒▒▒   ▒███  ▒███ ${ColorReset}"
    Write-Host "${ColorMagenta} █████   █████▒▒█████████  ████ █████▒▒██████  █████ █████${ColorReset}"
    Write-Host "${ColorMagenta}▒▒▒▒▒   ▒▒▒▒▒  ▒▒▒▒▒▒▒▒▒  ▒▒▒▒ ▒▒▒▒▒  ▒▒▒▒▒▒  ▒▒▒▒▒ ▒▒▒▒▒ ${ColorReset}"
    Write-Host ''
    Write-Host "${ColorCyan}${ColorBold}              Welcome to the AShell installer!${ColorReset}"
    Write-Host "${ColorDim}------------------------------------------------------------${ColorReset}"
    Write-Host ''
}

function Get-Python {
    $candidates = @('py', 'python3', 'python')
    foreach ($cmd in $candidates) {
        $path = Get-Command $cmd -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($path) {
            if ($cmd -eq 'py') {
                $versionText = & $cmd -3 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
                if (-not $versionText) { continue }
                return @{ Command = 'py'; Args = @('-3') ; Version = $versionText.Trim() }
            }
            else {
                $versionText = & $cmd -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
                return @{ Command = $cmd; Args = @(); Version = $versionText.Trim() }
            }
        }
    }
    Throw-Error "Python 3.8 or newer is required but was not found."
}

function Assert-PythonVersion {
    param($PythonInfo)
    $parts = $PythonInfo.Version.Split('.') | ForEach-Object {[int]$_}
    if ($parts[0] -lt 3 -or ($parts[0] -eq 3 -and $parts[1] -lt 8)) {
        Throw-Error "Python 3.8 or newer is required. Current version: $($PythonInfo.Version)"
    }
}

function Get-LatestReleaseAsset {
    param($ApiUrl)

    Write-Log "Fetching latest tag metadata..."
    $headers = @{ 'User-Agent' = 'AShell-Installer' }

    try {
        $response = Invoke-WebRequest -Uri $ApiUrl -Headers $headers
    }
    catch [System.Net.WebException] {
        $resp = $_.Exception.Response
        if ($resp -and ([int]$resp.StatusCode) -eq 404) {
            Throw-Error "No tags found for repository. Ensure tags exist before running the installer."
        }
        throw
    }

    $json = $response.Content | ConvertFrom-Json

    if (-not $json) {
        Throw-Error "Could not retrieve tag metadata from GitHub."
    }

    if ($json -isnot [System.Array]) {
        $json = @($json)
    }

    $best = $null
    foreach ($entry in $json) {
        $name = $entry.name
        $zipUrl = $entry.zipball_url
        if (-not $name -or -not $zipUrl) {
            continue
        }

        try {
            $version = [Version]$name
        }
        catch {
            continue
        }

        if (-not $best -or $version -gt $best.Version) {
            $best = [pscustomobject]@{ Version = $version; Url = $zipUrl }
        }
    }

    if (-not $best) {
        Throw-Error "Could not determine a downloadable zip from tags. Ensure tags follow 'major.minor.patch' format."
    }

    return $best.Url
}

function Download-ReleaseArchive {
    param($Url, $Destination)
    Write-Log "Downloading latest tagged source from $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
}

function Extract-Release {
    param($ArchivePath, $ExtractDir)
    Write-Log "Extracting release archive..."
    if (Test-Path $ExtractDir) { Remove-Item $ExtractDir -Recurse -Force }
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExtractDir -Force

    $entries = Get-ChildItem -LiteralPath $ExtractDir | Where-Object { $_.PSIsContainer -and $_.Name -ne '__MACOSX' }
    if (-not $entries) {
        Throw-Error "Failed to locate extracted source directory."
    }
    return $entries[0].FullName
}

function Copy-Source {
    param($SourceDir, $DestinationDir)
    if (Test-Path $DestinationDir) {
        Remove-Item $DestinationDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $DestinationDir | Out-Null
    Copy-Item -Path (Join-Path $SourceDir '*') -Destination $DestinationDir -Recurse -Force
}

function New-Venv {
    param($PythonInfo, $DestinationDir)
    Write-Log "Creating virtual environment..."
    & $PythonInfo.Command @($PythonInfo.Args + @('-m', 'venv', $DestinationDir))
}

function Install-Dependencies {
    param($VenvPath, $InstallDir)
    $pip = Join-Path $VenvPath 'Scripts\pip.exe'
    Write-Log "Upgrading pip..."
    & $pip install --upgrade pip | Out-Null

    $requirements = Join-Path $InstallDir 'requirements.txt'
    if (Test-Path $requirements) {
        Write-Log "Installing dependencies..."
        & $pip install -r $requirements | Out-Null
    }
    else {
        Write-Log "No requirements.txt found; skipping dependency installation."
    }
}

function Setup-Configuration {
    param($PythonInfo, $InstallDir)
    Write-Log "Preparing configuration..."
    if ($script:ReinstallMode) {
        Write-Log "Reinstall mode enabled; resetting configuration."
        if (Test-Path $ConfigFile) {
            Remove-Item $ConfigFile -Force -ErrorAction SilentlyContinue
        }
    }
    elseif (Test-Path $ConfigFile) {
        Write-Log "Existing configuration detected at $ConfigFile; skipping initialization."
        return
    }
    if (-not (Test-Path $ConfigDir)) {
        New-Item -ItemType Directory -Path $ConfigDir | Out-Null
    }

    $code = @"
import json
import os
import pathlib
import sys
import importlib.util

if len(sys.argv) >= 4:
    install_dir = pathlib.Path(sys.argv[1])
    config_dir = pathlib.Path(sys.argv[2])
    config_path = pathlib.Path(sys.argv[3])
else:
    env = os.environ
    install_dir = pathlib.Path(env['ASHELL_INSTALL_DIR'])
    config_dir = pathlib.Path(env['ASHELL_CONFIG_HOME'])
    config_path = pathlib.Path(env['ASHELL_CONFIG_FILE'])

config_dir.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location('ashell_install_shell', install_dir / 'shell.py')
module = importlib.util.module_from_spec(spec)
if not spec.loader:
    raise RuntimeError('Unable to load shell module for configuration setup')
spec.loader.exec_module(module)

default_config = getattr(module, 'DEFAULT_CONFIG', {}) or {}
config = json.loads(json.dumps(default_config))
prompt_config = config.get('prompt', {})

def ask_bool(question: str, default: bool) -> bool:
    suffix = ' [Y/n]' if default else ' [y/N]'
    while True:
        try:
            answer = input(f"{question}{suffix} ").strip().lower()
        except EOFError:
            return default
        if not answer:
            return default
        if answer in {'y', 'yes'}:
            return True
        if answer in {'n', 'no'}:
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

config['show_welcome_screen'] = ask_bool(
    'Show welcome screen?', bool(config.get('show_welcome_screen', True))
)

prompt_config['show_user_host'] = ask_bool(
    'Show user@host in prompt?', bool(prompt_config.get('show_user_host', True))
)

prompt_config['show_time'] = ask_bool(
    'Show time in prompt?', bool(prompt_config.get('show_time', True))
)

prompt_config['show_path'] = ask_bool(
    'Show path in prompt?', bool(prompt_config.get('show_path', True))
)

prompt_config['show_symbol'] = ask_bool(
    'Show prompt symbol?', bool(prompt_config.get('show_symbol', True))
)

prompt_config['symbol'] = ask_text(
    'Prompt symbol', str(prompt_config.get('symbol', '$')) or '$'
)

config['prompt'] = prompt_config

with config_path.open('w', encoding='utf-8') as handle:
    json.dump(config, handle, indent=2)

print(f"\nConfiguration written to {config_path}\n")
"@

    $venvDir = Join-Path $InstallDir '.venv'
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        $venvPython = Join-Path $venvDir 'bin/python'
    }
    if (-not (Test-Path $venvPython)) {
        Throw-Error "Virtual environment interpreter not found in $venvDir"
    }

    & $venvPython -c $code $InstallDir $ConfigDir $ConfigFile
    Write-Log "Configuration saved at $ConfigFile"
}

function Write-Launcher {
    param($InstallDir)
    $launcherPath = Join-Path $InstallDir 'ashell.cmd'
    $content = "@echo off`r`n" +
        '"%~dp0.venv\Scripts\python.exe" "%~dp0shell.py" %*' + "`r`n"
    Set-Content -LiteralPath $launcherPath -Value $content -Encoding Ascii
    return $launcherPath
}

function Ensure-Path {
    param($PathToAdd)
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $paths = $current -split ';' | Where-Object { $_ }
    if ($paths -notcontains $PathToAdd) {
        Write-Log "Adding $PathToAdd to user PATH"
        $newPath = if ($current) { "$current;$PathToAdd" } else { $PathToAdd }
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    }
}

function Main {
    Clear-Host
    Show-Banner

    if (Test-Path $InstallDir) {
        Write-Log "AShell is already installed at $InstallDir."
        $choice = Read-Host "Choose an action: [R]einstall, [D]elete, [A]bort"
        switch ($choice.ToLower()) {
            'r' {
                Write-Log "Reinstall selected; configuration will be reset."
                $script:ReinstallMode = $true
                if (Test-Path $ConfigFile) {
                    Remove-Item $ConfigFile -Force -ErrorAction SilentlyContinue
                }
            }
            'd' {
                Write-Log "Delete selected; removing existing installation."
                    Remove-Item $InstallDir -Recurse -Force -ErrorAction Stop
                    if (Test-Path $ConfigFile) {
                        Remove-Item $ConfigFile -Force -ErrorAction SilentlyContinue
                    }
                Write-Log "AShell installation removed."
        $tmpScript = [System.IO.Path]::GetTempFileName()
        Set-Content -LiteralPath $tmpScript -Value $code -Encoding UTF8

        try {
            $env:ASHELL_INSTALL_DIR = $InstallDir
            $env:ASHELL_CONFIG_HOME = $ConfigDir
            $env:ASHELL_CONFIG_FILE = $ConfigFile
            $env:PYTHONPATH = if ($env:PYTHONPATH) { "$InstallDir;$env:PYTHONPATH" } else { $InstallDir }
            & $venvPython $tmpScript $InstallDir $ConfigDir $ConfigFile
            Write-Log "Configuration saved at $ConfigFile"
        }
        finally {
            if (Test-Path $tmpScript) { Remove-Item $tmpScript -Force }
            Remove-Item Env:ASHELL_INSTALL_DIR -ErrorAction SilentlyContinue
            Remove-Item Env:ASHELL_CONFIG_HOME -ErrorAction SilentlyContinue
            Remove-Item Env:ASHELL_CONFIG_FILE -ErrorAction SilentlyContinue
            Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        }
            }
            'a' { Write-Log "Installation aborted by user."; return }
            ''  { Write-Log "Installation aborted by user."; return }
            default { Write-Log "Unknown choice; aborting."; return }
        }
    }

    $python = Get-Python
    Assert-PythonVersion -PythonInfo $python

    $temp = New-TemporaryFile
    Remove-Item $temp -Force
    $tempDir = New-Item -ItemType Directory -Path ([System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), [System.IO.Path]::GetRandomFileName()))

    try {
        Write-Section "Download"
        $archivePath = Join-Path $tempDir.FullName 'ashell.zip'
        $assetUrl = Get-LatestReleaseAsset -ApiUrl $ReleaseApi
        Download-ReleaseArchive -Url $assetUrl -Destination $archivePath

        Write-Section "Extract"
        $extracted = Extract-Release -ArchivePath $archivePath -ExtractDir (Join-Path $tempDir.FullName 'src')
        Copy-Source -SourceDir $extracted -DestinationDir $InstallDir

        Write-Section "Virtual Environment"
        $venvPath = Join-Path $InstallDir '.venv'
        New-Venv -PythonInfo $python -DestinationDir $venvPath
        Install-Dependencies -VenvPath $venvPath -InstallDir $InstallDir

        Write-Section "Configuration"
        Setup-Configuration -PythonInfo $python -InstallDir $InstallDir

        Write-Section "Final Touches"
        $launcher = Write-Launcher -InstallDir $InstallDir
        Ensure-Path -PathToAdd $InstallDir

        Write-Success "AShell installed successfully."
        Write-Log "Restart your terminal session, then run ${ColorBold}ashell${ColorReset} from any directory."
        Write-Log "Customize your shell via ${ColorBold}$ConfigFile${ColorReset}."
    }
    finally {
        if (Test-Path $tempDir.FullName) {
            Remove-Item $tempDir.FullName -Recurse -Force
        }
    }
}

Main