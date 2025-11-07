```
   █████████    █████████  █████               ████  ████ 
  ███▒▒▒▒▒███  ███▒▒▒▒▒███▒▒███               ▒▒███ ▒▒███ 
 ▒███    ▒███ ▒███    ▒▒▒  ▒███████    ██████  ▒███  ▒███ 
 ▒███████████ ▒▒█████████  ▒███▒▒███  ███▒▒███ ▒███  ▒███ 
 ▒███▒▒▒▒▒███  ▒▒▒▒▒▒▒▒███ ▒███ ▒███ ▒███████  ▒███  ▒███ 
 ▒███    ▒███  ███    ▒███ ▒███ ▒███ ▒███▒▒▒   ▒███  ▒███ 
 █████   █████▒▒█████████  ████ █████▒▒██████  █████ █████
▒▒▒▒▒   ▒▒▒▒▒  ▒▒▒▒▒▒▒▒▒  ▒▒▒▒ ▒▒▒▒▒  ▒▒▒▒▒▒  ▒▒▒▒▒ ▒▒▒▒▒ 
```

AShell is a minimal shell environment with built-in commands and a cool colorful prompt! The installers provided here set everything up for you, including a virtual environment, dependencies, and an interactive configuration wizard.
PS: Do not use this as an actual shell, this is just a funny experiment.

## Quick Install

### macOS & Linux

```bash
curl -fsSL https://raw.githubusercontent.com/DuperKnight/AShell/main/install.sh | bash
```

If AShell is already installed and you're piping via curl, stdin isn't a TTY, so the script can't prompt you. Supply your intent explicitly:

Reinstall (reset config):

```bash
curl -fsSL https://raw.githubusercontent.com/DuperKnight/AShell/main/install.sh | bash -s -- --reinstall
```

Delete existing install:

```bash
curl -fsSL https://raw.githubusercontent.com/DuperKnight/AShell/main/install.sh | bash -s -- --delete
```

Environment variable alternative:

```bash
ASHELL_ACTION=reinstall curl -fsSL https://raw.githubusercontent.com/DuperKnight/AShell/main/install.sh | bash -s --
```

After installation, restart your terminal or source your shell profile, then run:

```bash
ashell
```

Configuration lives at `~/.ashell/.ashell.conf`.

### Windows (PowerShell)

Run PowerShell as administrator (or with execution policy bypass):

```powershell
irm https://raw.githubusercontent.com/DuperKnight/AShell/main/install.ps1 | iex
```

Open a new terminal and start AShell with:

```powershell
ashell
```

Your configuration is stored at `%USERPROFILE%\.ashell\.ashell.conf`.


## Requirements

- Python 3.8 or later
- curl (macOS/Linux) or PowerShell 5.1+

## Installer CLI Flags

The installer accepts flags (pass them after `bash -s --` when using curl):

- `--reinstall` (`-r`) – reinstall over existing installation and reset configuration
- `--delete` (`-d`) – remove existing installation and exit
- `--abort` (`-a`) – abort if already installed (default when non-interactive and no flag/env provided)
- `--help` (`-h`) – show usage

You can also set the environment variable `ASHELL_ACTION` to `reinstall`, `delete`, or `abort`.
