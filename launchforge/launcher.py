"""Async program launcher with dependency-graph ordering."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque

from launchforge.config import LaunchForgeConfig, ProgramConfig

logger = logging.getLogger(__name__)


class ManagedProcess:
    """Wraps an asyncio subprocess with launch metadata."""

    def __init__(self, config: ProgramConfig) -> None:
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self.start_time: float = 0.0
        self.restart_count: int = 0
        self.last_exit_code: int | None = None

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    @property
    def uptime(self) -> float:
        if self.start_time == 0.0:
            return 0.0
        return time.monotonic() - self.start_time

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process else None

    async def launch(self) -> bool:
        """Attempt to launch the process.

        Returns ``True`` on success, ``False`` on failure.
        """
        cmd = [self.config.path, *self.config.args]
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self.start_time = time.monotonic()
            logger.info(
                "Started '%s' (pid=%s)", self.name, self.process.pid
            )
            return True
        except FileNotFoundError:
            logger.error(
                "Executable not found for '%s': %s", self.name, self.config.path
            )
            return False
        except PermissionError:
            logger.error(
                "Permission denied launching '%s': %s", self.name, self.config.path
            )
            return False

    async def stop(self) -> None:
        """Gracefully stop the process."""
        if self.process and self.process.returncode is None:
            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except TimeoutError:
                    self.process.kill()
                    await self.process.wait()
                logger.info("Stopped '%s'", self.name)
            except ProcessLookupError:
                pass  # Already gone


def _build_dependency_order(programs: list[ProgramConfig]) -> list[ProgramConfig]:
    """Return programs sorted by dependency order (topological sort).

    Programs with no dependencies come first; those that depend on others
    come after their dependencies.

    Raises:
        ValueError: If a circular dependency is detected (should already be
            caught by Pydantic validators, but kept as a safety net).
    """
    name_to_prog: dict[str, ProgramConfig] = {p.name: p for p in programs}
    in_degree: dict[str, int] = defaultdict(int)
    dependents: dict[str, list[str]] = defaultdict(list)

    for prog in programs:
        if prog.name not in in_degree:
            in_degree[prog.name] = 0
        for dep in prog.depends_on:
            in_degree[prog.name] += 1
            dependents[dep].append(prog.name)

    queue: deque[str] = deque(
        name for name in name_to_prog if in_degree[name] == 0
    )
    ordered: list[ProgramConfig] = []

    while queue:
        current = queue.popleft()
        ordered.append(name_to_prog[current])
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(ordered) != len(programs):
        raise ValueError("Circular dependency detected in program list.")

    return ordered


class Launcher:
    """Manages the async launching of all configured programs."""

    def __init__(self, config: LaunchForgeConfig) -> None:
        self.config = config
        self._processes: dict[str, ManagedProcess] = {}
        self._shutdown_event = asyncio.Event()

    @property
    def processes(self) -> dict[str, ManagedProcess]:
        return self._processes

    async def start_all(self) -> None:
        """Launch all enabled programs in dependency order."""
        enabled = [p for p in self.config.programs if p.enabled]
        ordered = _build_dependency_order(enabled)

        for prog_cfg in ordered:
            managed = ManagedProcess(prog_cfg)
            self._processes[prog_cfg.name] = managed

            max_retries = self.config.settings.max_retries
            success = False
            for attempt in range(max_retries + 1):
                success = await managed.launch()
                if success:
                    break
                if attempt < max_retries:
                    logger.info(
                        "Retrying '%s' in %.1fs (attempt %d/%d)...",
                        prog_cfg.name,
                        prog_cfg.retry_delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(prog_cfg.retry_delay)
                else:
                    logger.error(
                        "Failed to start '%s' after %d attempt(s). Skipping.",
                        prog_cfg.name,
                        max_retries + 1,
                    )

            if success and prog_cfg.delay > 0:
                logger.info(
                    "Waiting %.1fs after launching '%s'...",
                    prog_cfg.delay,
                    prog_cfg.name,
                )
                await asyncio.sleep(prog_cfg.delay)

    async def stop_all(self) -> None:
        """Stop all managed processes in reverse launch order."""
        names = list(self._processes.keys())
        for name in reversed(names):
            await self._processes[name].stop()

    async def restart(self, name: str) -> bool:
        """Restart a single named process.

        Returns ``True`` if successfully restarted.
        """
        managed = self._processes.get(name)
        if managed is None:
            logger.warning("Cannot restart unknown program '%s'.", name)
            return False
        await managed.stop()
        success = await managed.launch()
        if success:
            managed.restart_count += 1
        return success

    def signal_shutdown(self) -> None:
        """Signal the launcher to initiate a graceful shutdown."""
        self._shutdown_event.set()
