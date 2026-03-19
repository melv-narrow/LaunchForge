# LaunchForge

[![CI](https://github.com/melv-narrow/LaunchForge/actions/workflows/ci.yml/badge.svg)](https://github.com/melv-narrow/LaunchForge/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**LaunchForge** is a modern, async-first startup program manager for Windows. It launches your configured applications on login — in the right order, with health monitoring, crash recovery, and a system-tray UI.

---

## ✨ Features (v2)

| Feature | v1 | v2 |
|---|---|---|
| Async program launch | ❌ sequential `time.sleep` | ✅ `asyncio.create_subprocess_exec` |
| Dependency ordering | ❌ | ✅ topological sort via `depends_on` |
| Config format | JSON | TOML (with comments) |
| Config validation | manual `validate_config()` | ✅ Pydantic v2 models |
| Launch profiles | ❌ | ✅ `--profile gaming` / `--profile work` |
| Health monitoring | basic `process.poll()` | ✅ `psutil` CPU/memory tracking |
| Crash recovery | ❌ buggy retry logic | ✅ fixed, per-program `retry_delay` |
| Logging | `logging.basicConfig` flat file | ✅ `RotatingFileHandler` + optional `structlog` JSON |
| System tray | tkinter window | ✅ `pystray` tray icon with context menu |
| Desktop notifications | ❌ | ✅ `plyer` crash notifications |
| CLI | single script | ✅ `click` subcommands (`run`, `status`, `install`, `uninstall`) |
| Auto-start setup | manual shortcut | ✅ `launchforge install` (Task Scheduler) |
| Packaging | no package | ✅ `pyproject.toml`, installable via `pip` |
| Tests | broken `test_main.py` | ✅ `pytest` + `pytest-asyncio`, 38 tests |
| CI | ❌ | ✅ GitHub Actions (lint + test, Python 3.11/3.12) |

---

## 🗂️ Project Structure

```
LaunchForge/
├── .github/
│   └── workflows/
│       └── ci.yml          # Lint + test on every push/PR
├── launchforge/
│   ├── __init__.py
│   ├── __main__.py         # python -m launchforge
│   ├── cli.py              # click CLI (run / status / install / uninstall)
│   ├── config.py           # Pydantic v2 models + TOML loading
│   ├── launcher.py         # Async launch logic + dependency graph
│   ├── monitor.py          # Health-check loop (psutil)
│   ├── tray.py             # pystray system-tray UI
│   └── notifications.py    # plyer desktop notifications
├── tests/
│   ├── __init__.py
│   ├── test_config.py      # Config validation tests
│   ├── test_launcher.py    # Launcher + dependency-order tests
│   └── test_monitor.py     # Health-monitor tests
├── config.toml             # Default config (6 programs, edit to match your setup)
├── pyproject.toml          # Packaging + tool config
├── .gitignore
├── startup_apps.py         # DEPRECATED — v1 reference
└── startup_gui.py          # DEPRECATED — v1 reference
```

---

## 🚀 Installation

### From source (recommended during development)

```bash
git clone https://github.com/melv-narrow/LaunchForge.git
cd LaunchForge
pip install -e ".[dev]"
```

### Optional extras

```bash
pip install "launchforge[tray]"     # pystray + Pillow system-tray icon
pip install "launchforge[notify]"   # plyer desktop notifications
pip install "launchforge[log]"      # structlog JSON logging
pip install "launchforge[all]"      # everything above
```

### Register with Windows Task Scheduler (auto-start on login)

```bash
launchforge install
```

To remove:

```bash
launchforge uninstall
```

---

## ⚙️ Configuration (`config.toml`)

Edit `config.toml` in the project root (or pass `--config /path/to/config.toml`):

```toml
[settings]
health_check_interval = 30   # seconds between health checks
max_retries = 3
profile = "default"          # "default" = all programs; or a group name

[[programs]]
name = "Voicemeeter"
path = "C:/Program Files (x86)/VB/Voicemeeter/voicemeeter8.exe"
delay = 10          # wait N seconds after launching before starting next
retry_delay = 5     # wait N seconds between retry attempts
group = "audio"

[[programs]]
name = "Wallpaper Engine"
path = "D:/SteamLibrary/steamapps/common/wallpaper_engine/wallpaper64.exe"
delay = 15
depends_on = ["Voicemeeter"]   # won't start until Voicemeeter is launched
group = "desktop"

[[programs]]
name = "Steam"
path = "C:/Program Files (x86)/Steam/steam.exe"
delay = 5
depends_on = ["Wallpaper Engine"]
group = "gaming"
```

### Field reference

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | **required** | Unique display name |
| `path` | string | **required** | Full path to the executable |
| `delay` | float | `0` | Seconds to wait *after* launching this program |
| `retry_delay` | float | `5` | Seconds between retry attempts on failure |
| `args` | list[string] | `[]` | Command-line arguments |
| `depends_on` | list[string] | `[]` | Names of programs that must launch first |
| `group` | string | `"default"` | Logical group / profile name |
| `enabled` | bool | `true` | Set to `false` to skip without removing |

---

## 💻 CLI Usage

```bash
# Launch all programs (default config.toml)
launchforge run

# Launch only "gaming" group programs
launchforge run --profile gaming

# Use a custom config file, no tray icon
launchforge run --config ~/myconfig.toml --no-tray

# Preview configured programs
launchforge status

# Register auto-start entry (Windows Task Scheduler)
launchforge install

# Remove auto-start entry
launchforge uninstall

# Show version
launchforge --version
```

---

## 🧪 Running Tests

```bash
pip install -e ".[dev]"
pytest
```

Expected output:

```
38 passed in 0.21s
```

---

## 🔧 Development

```bash
# Lint
ruff check launchforge/ tests/

# Auto-fix lint issues
ruff check --fix launchforge/ tests/
```

---

## 📋 Bugs Fixed from v1

| Bug | v1 | v2 |
|---|---|---|
| Inverted retry logic | `retry_delay` sleep ran on the **wrong** attempt | Fixed: sleep before each retry, not after the last |
| `KeyError` on `program['args']` in health-check restart | Always crashed on restart | Fixed: uses `.get('args', [])` pattern via Pydantic defaults |
| Log file grows unbounded | `logging.basicConfig` flat file | `RotatingFileHandler` with configurable size & backup count |

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
