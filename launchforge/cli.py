"""CLI entry point for LaunchForge using click."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import logging.handlers
import signal
import sys
from pathlib import Path

import click

from launchforge import __version__
from launchforge.config import load_config
from launchforge.launcher import Launcher
from launchforge.monitor import HealthMonitor
from launchforge.notifications import send_notification

try:
    from rich.console import Console
    from rich.table import Table
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(log_file: str, max_bytes: int, backup_count: int) -> None:
    """Configure rotating file handler + console handler with structlog-style
    format when structlog is available, otherwise use standard logging."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    try:
        import structlog  # type: ignore[import-untyped]

        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    except ImportError:
        pass  # structlog is optional


# ---------------------------------------------------------------------------
# Rich status table
# ---------------------------------------------------------------------------

def _print_status_table(launcher: Launcher) -> None:
    """Print a Rich table of process status, or plain text as fallback."""
    if _RICH_AVAILABLE:
        console = Console()
        table = Table(title="LaunchForge — Process Status", show_lines=True)
        table.add_column("Name", style="bold cyan")
        table.add_column("Group")
        table.add_column("Status")
        table.add_column("PID")
        table.add_column("Uptime (s)")
        table.add_column("Restarts")
        for name, proc in launcher.processes.items():
            status = "[green]Running[/]" if proc.is_running else "[red]Stopped[/]"
            table.add_row(
                name,
                proc.config.group,
                status,
                str(proc.pid or "—"),
                f"{proc.uptime:.0f}",
                str(proc.restart_count),
            )
        console.print(table)
    else:
        print("Name | Group | Running | PID | Uptime | Restarts")
        for name, proc in launcher.processes.items():
            print(
                f"{name} | {proc.config.group} | {proc.is_running} | "
                f"{proc.pid} | {proc.uptime:.0f}s | {proc.restart_count}"
            )


# ---------------------------------------------------------------------------
# Main async runtime
# ---------------------------------------------------------------------------

async def _run(config_path: Path, profile: str | None, no_tray: bool) -> None:
    """Core async runtime: launch programs, start monitor, wait for shutdown."""
    cfg = load_config(config_path, profile=profile)
    settings = cfg.settings

    _setup_logging(settings.log_file, settings.log_max_bytes, settings.log_backup_count)
    logger.info("LaunchForge v%s starting. Profile: %s", __version__, settings.profile)

    launcher = Launcher(cfg)

    # Signal handling
    loop = asyncio.get_running_loop()

    def _on_signal() -> None:
        logger.info("Shutdown signal received.")
        launcher.signal_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, OSError):
            loop.add_signal_handler(sig, _on_signal)

    # Optional system tray
    if not no_tray:
        try:
            from launchforge.tray import start_tray_thread
            start_tray_thread(launcher, loop)
        except (ImportError, OSError, RuntimeError) as exc:
            logger.debug("Tray not started: %s", exc)

    # Launch all programs
    await launcher.start_all()
    _print_status_table(launcher)

    # Start health monitor
    monitor = HealthMonitor(
        launcher,
        interval=settings.health_check_interval,
        notify=send_notification,
    )
    monitor_task = asyncio.create_task(monitor.run())

    # Wait until shutdown is signalled
    await launcher._shutdown_event.wait()

    # Graceful shutdown
    logger.info("Shutting down...")
    monitor_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await monitor_task
    await launcher.stop_all()
    logger.info("LaunchForge stopped.")


# ---------------------------------------------------------------------------
# Windows Task Scheduler helpers
# ---------------------------------------------------------------------------

def _scheduler_task_name() -> str:
    return "LaunchForge"


def _install_scheduler() -> None:
    """Register LaunchForge as a Windows Task Scheduler entry."""
    import shutil
    import subprocess

    python = shutil.which("python") or sys.executable
    launchforge_cmd = f'"{python}" -m launchforge'
    task_name = _scheduler_task_name()

    cmd = [
        "schtasks", "/create", "/tn", task_name,
        "/tr", launchforge_cmd,
        "/sc", "ONLOGON",
        "/rl", "HIGHEST",
        "/f",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        click.echo(f"✅ Task '{task_name}' registered in Windows Task Scheduler.")
    except FileNotFoundError:
        click.echo("❌ schtasks not found. This command requires Windows.", err=True)
    except subprocess.CalledProcessError as exc:
        click.echo(f"❌ Failed to register task: {exc.stderr}", err=True)


def _uninstall_scheduler() -> None:
    """Remove the LaunchForge Task Scheduler entry."""
    import subprocess

    task_name = _scheduler_task_name()
    cmd = ["schtasks", "/delete", "/tn", task_name, "/f"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        click.echo(f"✅ Task '{task_name}' removed from Windows Task Scheduler.")
    except FileNotFoundError:
        click.echo("❌ schtasks not found. This command requires Windows.", err=True)
    except subprocess.CalledProcessError as exc:
        click.echo(f"❌ Failed to remove task: {exc.stderr}", err=True)


# ---------------------------------------------------------------------------
# Click CLI
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="launchforge")
def main() -> None:
    """LaunchForge — async startup program manager."""


@main.command("run")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=False, path_type=Path),
    default="config.toml",
    show_default=True,
    help="Path to the TOML config file.",
)
@click.option("--profile", default=None, help="Launch profile (filters by group).")
@click.option("--no-tray", is_flag=True, default=False, help="Disable system tray icon.")
def cmd_run(config_path: Path, profile: str | None, no_tray: bool) -> None:
    """Launch all configured startup programs."""
    asyncio.run(_run(config_path, profile, no_tray))


@main.command("status")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=False, path_type=Path),
    default="config.toml",
    show_default=True,
    help="Path to the TOML config file.",
)
@click.option("--profile", default=None, help="Launch profile.")
def cmd_status(config_path: Path, profile: str | None) -> None:
    """Show configured programs (config preview, not live status)."""
    try:
        cfg = load_config(config_path, profile=profile)
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        sys.exit(1)

    if _RICH_AVAILABLE:
        console = Console()
        table = Table(title="LaunchForge Config", show_lines=True)
        table.add_column("Name", style="bold cyan")
        table.add_column("Path")
        table.add_column("Group")
        table.add_column("Delay (s)")
        table.add_column("Depends on")
        for prog in cfg.programs:
            table.add_row(
                prog.name,
                prog.path,
                prog.group,
                str(prog.delay),
                ", ".join(prog.depends_on) or "—",
            )
        console.print(table)
    else:
        for prog in cfg.programs:
            click.echo(f"{prog.name}: {prog.path} (group={prog.group}, delay={prog.delay}s)")


@main.command("install")
def cmd_install() -> None:
    """Register LaunchForge to auto-start via Windows Task Scheduler."""
    _install_scheduler()


@main.command("uninstall")
def cmd_uninstall() -> None:
    """Remove the LaunchForge Task Scheduler entry."""
    _uninstall_scheduler()
