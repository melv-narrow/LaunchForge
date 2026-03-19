"""Health-check monitor using psutil for crash detection and restart."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PSUTIL_AVAILABLE = False

from launchforge.launcher import Launcher, ManagedProcess

logger = logging.getLogger(__name__)

# Type alias for the optional notification callback
NotifyCallback = Callable[[str, str], Coroutine]


class HealthMonitor:
    """Periodically checks managed processes and restarts crashed ones."""

    def __init__(
        self,
        launcher: Launcher,
        interval: float = 30.0,
        notify: NotifyCallback | None = None,
    ) -> None:
        self.launcher = launcher
        self.interval = interval
        self._notify = notify
        self._running = False

    async def run(self) -> None:
        """Start the health-check loop until cancelled."""
        self._running = True
        logger.info(
            "Health monitor started (interval=%.1fs)", self.interval
        )
        try:
            while self._running:
                await asyncio.sleep(self.interval)
                await self._check_all()
        except asyncio.CancelledError:
            logger.info("Health monitor stopped.")
            raise

    def stop(self) -> None:
        """Signal the monitor loop to stop after the current check."""
        self._running = False

    async def _check_all(self) -> None:
        """Check every managed process and restart if terminated."""
        for _name, managed in list(self.launcher.processes.items()):
            if not managed.config.enabled:
                continue
            await self._check_process(managed)

    async def _check_process(self, managed: ManagedProcess) -> None:
        """Inspect a single process and restart if it has exited."""
        proc = managed.process
        if proc is None:
            return

        exit_code = proc.returncode
        if exit_code is not None:
            managed.last_exit_code = exit_code
            logger.warning(
                "'%s' (pid=%s) exited with code %s. Restarting...",
                managed.name,
                managed.pid,
                exit_code,
            )
            if self._notify:
                try:
                    await self._notify(
                        managed.name,
                        f"Process '{managed.name}' crashed (exit={exit_code}). Restarting...",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Notification error: %s", exc)

            success = await self.launcher.restart(managed.name)
            if success:
                managed.restart_count += 1
                logger.info("Successfully restarted '%s'.", managed.name)
            else:
                logger.error("Failed to restart '%s'.", managed.name)
            return

        # Extra health info via psutil (CPU/memory) when available
        if _PSUTIL_AVAILABLE and managed.pid is not None:
            try:
                ps_proc = psutil.Process(managed.pid)
                cpu = ps_proc.cpu_percent(interval=None)
                mem = ps_proc.memory_info().rss / (1024 * 1024)
                logger.debug(
                    "'%s' — CPU=%.1f%% MEM=%.1fMB", managed.name, cpu, mem
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
