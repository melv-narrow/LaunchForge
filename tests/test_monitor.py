"""Tests for launchforge.monitor — health-check loop and restart logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from launchforge.config import LaunchForgeConfig, ProgramConfig, SettingsConfig
from launchforge.launcher import Launcher, ManagedProcess
from launchforge.monitor import HealthMonitor


def _make_launcher(programs=None) -> Launcher:
    cfg = LaunchForgeConfig(
        settings=SettingsConfig(max_retries=1, health_check_interval=1),
        programs=programs or [],
    )
    return Launcher(cfg)


class TestHealthMonitor:
    @pytest.mark.asyncio
    async def test_restarts_crashed_process(self):
        """Monitor should call launcher.restart when process exits."""
        launcher = _make_launcher(
            programs=[ProgramConfig(name="App", path="/bin/app", delay=0)]
        )

        # Manually inject a "running" process that appears crashed (returncode=1)
        crashed_proc = MagicMock()
        crashed_proc.pid = 42
        crashed_proc.returncode = 1  # process has exited

        managed = ManagedProcess(ProgramConfig(name="App", path="/bin/app"))
        managed.process = crashed_proc
        launcher._processes["App"] = managed

        # Mock launcher.restart to succeed
        launcher.restart = AsyncMock(return_value=True)

        monitor = HealthMonitor(launcher, interval=0.01)
        await monitor._check_all()

        launcher.restart.assert_awaited_once_with("App")

    @pytest.mark.asyncio
    async def test_no_restart_when_running(self):
        """Monitor should not restart a healthy process."""
        launcher = _make_launcher(
            programs=[ProgramConfig(name="App", path="/bin/app", delay=0)]
        )

        running_proc = MagicMock()
        running_proc.pid = 42
        running_proc.returncode = None  # still running

        managed = ManagedProcess(ProgramConfig(name="App", path="/bin/app"))
        managed.process = running_proc
        launcher._processes["App"] = managed

        launcher.restart = AsyncMock(return_value=True)

        monitor = HealthMonitor(launcher, interval=0.01)

        # Patch psutil to avoid real process lookup
        with patch("launchforge.monitor._PSUTIL_AVAILABLE", False):
            await monitor._check_all()

        launcher.restart.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notify_called_on_crash(self):
        """Notification callback should be invoked when process crashes."""
        launcher = _make_launcher(
            programs=[ProgramConfig(name="App", path="/bin/app", delay=0)]
        )

        crashed_proc = MagicMock()
        crashed_proc.pid = 10
        crashed_proc.returncode = -1

        managed = ManagedProcess(ProgramConfig(name="App", path="/bin/app"))
        managed.process = crashed_proc
        launcher._processes["App"] = managed

        launcher.restart = AsyncMock(return_value=True)

        notify_mock = AsyncMock()
        monitor = HealthMonitor(launcher, interval=0.01, notify=notify_mock)
        await monitor._check_all()

        notify_mock.assert_awaited_once()
        call_args = notify_mock.call_args[0]
        assert "App" in call_args[0]

    @pytest.mark.asyncio
    async def test_monitor_stops_on_cancel(self):
        """HealthMonitor.run() should exit cleanly when cancelled."""
        launcher = _make_launcher()
        monitor = HealthMonitor(launcher, interval=100)

        import asyncio

        task = asyncio.create_task(monitor.run())
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_disabled_program_skipped(self):
        """Monitor should skip programs with enabled=False."""
        launcher = _make_launcher()

        crashed_proc = MagicMock()
        crashed_proc.pid = 7
        crashed_proc.returncode = 1

        managed = ManagedProcess(
            ProgramConfig(name="App", path="/bin/app", enabled=False)
        )
        managed.process = crashed_proc
        launcher._processes["App"] = managed

        launcher.restart = AsyncMock(return_value=True)
        monitor = HealthMonitor(launcher, interval=0.01)
        await monitor._check_all()

        launcher.restart.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_process_object_skipped(self):
        """Monitor should skip managed entries with no process yet."""
        launcher = _make_launcher()

        managed = ManagedProcess(ProgramConfig(name="App", path="/bin/app"))
        # process is None — not yet launched
        launcher._processes["App"] = managed

        launcher.restart = AsyncMock(return_value=True)
        monitor = HealthMonitor(launcher, interval=0.01)
        await monitor._check_all()

        launcher.restart.assert_not_awaited()
