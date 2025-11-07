#Requires -Version 5.1

param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "AShell"),
    [string]$ReleaseApi = "https://api.github.com/repos/DuperKnight/AShell/releases/latest"
)

$ConfigDir = Join-Path $env:USERPROFILE '.ashell'
$ConfigFile = Join-Path $ConfigDir '.ashell.conf'

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Log {
    param([string]$Message)
    Write-Host $Message
}

function Throw-Error {
    param([string]$Message)
    throw $Message
}

function Show-Banner {
    Write-Host ''
    Write-Host '   █████████    █████████  █████               ████  ████ ' -ForegroundColor Magenta
    Write-Host '  ███▒▒▒▒▒███  ███▒▒▒▒▒███▒▒███               ▒▒███ ▒▒███ ' -ForegroundColor Magenta
    Write-Host ' ▒███    ▒███ ▒███    ▒▒▒  ▒███████    ██████  ▒███  ▒███ ' -ForegroundColor Magenta
    Write-Host ' ▒███████████ ▒▒█████████  ▒███▒▒███  ███▒▒███ ▒███  ▒███ ' -ForegroundColor Magenta
    Write-Host ' ▒███▒▒▒▒▒███  ▒▒▒▒▒▒▒▒███ ▒███ ▒███ ▒███████  ▒███  ▒███ ' -ForegroundColor Magenta
    Write-Host ' ▒███    ▒███  ███    ▒███ ▒███ ▒███ ▒███▒▒▒   ▒███  ▒███ ' -ForegroundColor Magenta
    Write-Host ' █████   █████▒▒█████████  ████ █████▒▒██████  █████ █████' -ForegroundColor Magenta
    Write-Host '▒▒▒▒▒   ▒▒▒▒▒  ▒▒▒▒▒▒▒▒▒  ▒▒▒▒ ▒▒▒▒▒  ▒▒▒▒▒▒  ▒▒▒▒▒ ▒▒▒▒▒ ' -ForegroundColor Magenta
    Write-Host ''
    Write-Host '              Welcome to the AShell installer!' -ForegroundColor Cyan
    Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray
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

    Write-Log "Fetching latest release metadata..."
    $headers = @{ 'User-Agent' = 'AShell-Installer' }
    $response = Invoke-WebRequest -Uri $ApiUrl -Headers $headers
    $json = $response.Content | ConvertFrom-Json

    $asset = $json.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
    if (-not $asset) {
        if ($json.zipball_url) {
            return $json.zipball_url
        }
        Throw-Error "Could not find a downloadable asset for the latest release."
    }
    return $asset.browser_download_url
}

function Download-ReleaseArchive {
    param($Url, $Destination)
    Write-Log "Downloading latest release from $Url"
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
    if (-not (Test-Path $ConfigDir)) {
        New-Item -ItemType Directory -Path $ConfigDir | Out-Null
    }

    $code = @"
import json
import pathlib
import sys
import importlib.util

install_dir = pathlib.Path(sys.argv[1])
config_dir = pathlib.Path(sys.argv[2])
config_path = pathlib.Path(sys.argv[3])

config_dir.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location('ashell_install_shell', install_dir / 'shell.py')
module = importlib.util.module_from_spec(spec)
if not spec.loader:
    raise RuntimeError('Unable to load shell module for configuration setup')
spec.loader.exec_module(module)

write_status = sys.stdout.write
default_config = getattr(module, 'DEFAULT_CONFIG', {}) or {}

def write_default():
    with config_path.open('w', encoding='utf-8') as handle:
        json.dump(default_config, handle, indent=2)

if not config_path.exists():
    write_default()
    write_status('created')
else:
    try:
        with config_path.open('r', encoding='utf-8') as handle:
            existing = json.load(handle)
        if not isinstance(existing, dict):
            raise ValueError('Configuration root must be an object')
        write_status('kept')
    except Exception:
        backup_path = config_path.with_suffix(config_path.suffix + '.bak')
        try:
            config_path.replace(backup_path)
        except Exception:
            pass
        write_default()
        write_status(f'reset:{backup_path}')
"@

    $args = @()
    if ($PythonInfo.Args) { $args += $PythonInfo.Args }
    $args += @('-c', $code, $InstallDir, $ConfigDir, $ConfigFile)
    $result = & $PythonInfo.Command @args

    if ($result -eq 'created') {
        Write-Log "Configuration created at $ConfigFile"
    }
    elseif ($result -eq 'kept') {
        Write-Log "Existing configuration preserved at $ConfigFile"
    }
    elseif ($result -like 'reset:*') {
        $backup = $result.Substring(6)
        Write-Log "Existing configuration was invalid; backup saved to $backup and defaults restored."
    }
    else {
        Write-Log "Configuration stored at $ConfigFile"
    }
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
    Show-Banner
    $python = Get-Python
    Assert-PythonVersion -PythonInfo $python

    $temp = New-TemporaryFile
    Remove-Item $temp -Force
    $tempDir = New-Item -ItemType Directory -Path ([System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), [System.IO.Path]::GetRandomFileName()))

    try {
        $archivePath = Join-Path $tempDir.FullName 'ashell.zip'
        $assetUrl = Get-LatestReleaseAsset -ApiUrl $ReleaseApi
        Download-ReleaseArchive -Url $assetUrl -Destination $archivePath

        $extracted = Extract-Release -ArchivePath $archivePath -ExtractDir (Join-Path $tempDir.FullName 'src')
        Copy-Source -SourceDir $extracted -DestinationDir $InstallDir

        $venvPath = Join-Path $InstallDir '.venv'
        New-Venv -PythonInfo $python -DestinationDir $venvPath
        Install-Dependencies -VenvPath $venvPath -InstallDir $InstallDir
        Setup-Configuration -PythonInfo $python -InstallDir $InstallDir

        $launcher = Write-Launcher -InstallDir $InstallDir
        Ensure-Path -PathToAdd $InstallDir

        Write-Log "AShell installed successfully. Restart your terminal session, then run 'ashell' from any directory."
        Write-Log "Customize your shell via $ConfigFile."
    }
    finally {
        if (Test-Path $tempDir.FullName) {
            Remove-Item $tempDir.FullName -Recurse -Force
        }
    }
}

Main