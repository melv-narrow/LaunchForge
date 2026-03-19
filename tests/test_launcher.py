"""Tests for launchforge.launcher — async launch logic and dependency graph."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from launchforge.config import LaunchForgeConfig, ProgramConfig, SettingsConfig
from launchforge.launcher import Launcher, ManagedProcess, _build_dependency_order

# ---------------------------------------------------------------------------
# _build_dependency_order
# ---------------------------------------------------------------------------

class TestBuildDependencyOrder:
    def test_no_dependencies(self):
        progs = [
            ProgramConfig(name="A", path="/bin/a"),
            ProgramConfig(name="B", path="/bin/b"),
        ]
        ordered = _build_dependency_order(progs)
        assert {p.name for p in ordered} == {"A", "B"}

    def test_simple_chain(self):
        progs = [
            ProgramConfig(name="B", path="/bin/b", depends_on=["A"]),
            ProgramConfig(name="A", path="/bin/a"),
        ]
        ordered = _build_dependency_order(progs)
        names = [p.name for p in ordered]
        assert names.index("A") < names.index("B")

    def test_diamond_dependency(self):
        """A → B, A → C, B → D, C → D  (D must come last)."""
        progs = [
            ProgramConfig(name="D", path="/bin/d", depends_on=["B", "C"]),
            ProgramConfig(name="B", path="/bin/b", depends_on=["A"]),
            ProgramConfig(name="C", path="/bin/c", depends_on=["A"]),
            ProgramConfig(name="A", path="/bin/a"),
        ]
        ordered = _build_dependency_order(progs)
        names = [p.name for p in ordered]
        assert names.index("A") < names.index("B")
        assert names.index("A") < names.index("C")
        assert names.index("B") < names.index("D")
        assert names.index("C") < names.index("D")

    def test_single_program(self):
        progs = [ProgramConfig(name="Solo", path="/bin/solo")]
        ordered = _build_dependency_order(progs)
        assert len(ordered) == 1


# ---------------------------------------------------------------------------
# ManagedProcess
# ---------------------------------------------------------------------------

class TestManagedProcess:
    def test_initial_state(self):
        cfg = ProgramConfig(name="App", path="/bin/app")
        mp = ManagedProcess(cfg)
        assert mp.is_running is False
        assert mp.pid is None
        assert mp.uptime == 0.0
        assert mp.restart_count == 0

    @pytest.mark.asyncio
    async def test_launch_success(self):
        cfg = ProgramConfig(name="App", path="/bin/app")
        mp = ManagedProcess(cfg)

        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_proc.returncode = None

        with patch(
            "launchforge.launcher.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            result = await mp.launch()

        assert result is True
        assert mp.is_running is True
        assert mp.pid == 1234

    @pytest.mark.asyncio
    async def test_launch_file_not_found(self):
        cfg = ProgramConfig(name="App", path="/nonexistent/app")
        mp = ManagedProcess(cfg)

        with patch(
            "launchforge.launcher.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=FileNotFoundError),
        ):
            result = await mp.launch()

        assert result is False
        assert mp.is_running is False

    @pytest.mark.asyncio
    async def test_stop(self):
        cfg = ProgramConfig(name="App", path="/bin/app")
        mp = ManagedProcess(cfg)

        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.wait = AsyncMock(return_value=0)
        mp.process = mock_proc

        await mp.stop()
        mock_proc.terminate.assert_called_once()


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------

class TestLauncher:
    def _make_cfg(self, programs=None) -> LaunchForgeConfig:
        return LaunchForgeConfig(
            settings=SettingsConfig(max_retries=1, health_check_interval=30),
            programs=programs or [],
        )

    @pytest.mark.asyncio
    async def test_start_all_calls_launch(self):
        cfg = self._make_cfg(
            programs=[ProgramConfig(name="App", path="/bin/app", delay=0)]
        )
        launcher = Launcher(cfg)

        mock_proc = MagicMock()
        mock_proc.pid = 42
        mock_proc.returncode = None

        with patch(
            "launchforge.launcher.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            await launcher.start_all()

        assert "App" in launcher.processes
        assert launcher.processes["App"].is_running is True

    @pytest.mark.asyncio
    async def test_start_all_retries_on_failure(self):
        cfg = self._make_cfg(
            programs=[ProgramConfig(name="App", path="/bin/app", delay=0, retry_delay=0)]
        )
        launcher = Launcher(cfg)

        call_count = 0
        mock_proc = MagicMock()
        mock_proc.pid = 99
        mock_proc.returncode = None

        async def _fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise FileNotFoundError
            return mock_proc

        with patch("launchforge.launcher.asyncio.create_subprocess_exec", new=_fake_exec):
            await launcher.start_all()

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_stop_all_calls_terminate(self):
        cfg = self._make_cfg(
            programs=[ProgramConfig(name="App", path="/bin/app", delay=0)]
        )
        launcher = Launcher(cfg)

        mock_proc = MagicMock()
        mock_proc.pid = 10
        mock_proc.returncode = None
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "launchforge.launcher.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            await launcher.start_all()

        await launcher.stop_all()
        mock_proc.terminate.assert_called()

    @pytest.mark.asyncio
    async def test_restart(self):
        cfg = self._make_cfg(
            programs=[ProgramConfig(name="App", path="/bin/app", delay=0)]
        )
        launcher = Launcher(cfg)

        mock_proc = MagicMock()
        mock_proc.pid = 5
        mock_proc.returncode = None
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "launchforge.launcher.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            await launcher.start_all()
            result = await launcher.restart("App")

        assert result is True

    @pytest.mark.asyncio
    async def test_restart_unknown_returns_false(self):
        cfg = self._make_cfg()
        launcher = Launcher(cfg)
        result = await launcher.restart("Ghost")
        assert result is False

    def test_signal_shutdown(self):
        cfg = self._make_cfg()
        launcher = Launcher(cfg)
        assert not launcher._shutdown_event.is_set()
        launcher.signal_shutdown()
        assert launcher._shutdown_event.is_set()
