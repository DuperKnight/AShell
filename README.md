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
