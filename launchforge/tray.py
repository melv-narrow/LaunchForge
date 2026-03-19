"""System-tray application using pystray + Pillow (optional)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

try:
    import pystray  # type: ignore[import-untyped]
    from PIL import Image, ImageDraw  # type: ignore[import-untyped]
    _TRAY_AVAILABLE = True
except ImportError:
    _TRAY_AVAILABLE = False

if TYPE_CHECKING:
    from launchforge.launcher import Launcher


def _make_icon_image(size: int = 64) -> Image.Image:
    """Generate a simple coloured square icon when no image file exists."""
    img = Image.new("RGBA", (size, size), color=(30, 30, 30, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, size - 8, size - 8], fill=(0, 180, 100, 255))
    return img


class TrayApp:
    """Manages a system-tray icon with start/stop/restart menu items."""

    def __init__(self, launcher: Launcher, loop: asyncio.AbstractEventLoop) -> None:
        self.launcher = launcher
        self.loop = loop
        self._icon: pystray.Icon | None = None

    # ------------------------------------------------------------------
    # Menu action helpers (called from tray thread, schedule on asyncio loop)
    # ------------------------------------------------------------------

    def _schedule(self, coro) -> None:
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def _on_stop_all(self, icon: Any, item: Any) -> None:
        logger.info("Tray: stop all requested.")
        self._schedule(self.launcher.stop_all())

    def _on_quit(self, icon: Any, item: Any) -> None:
        logger.info("Tray: quit requested.")
        self._schedule(self.launcher.stop_all())
        self.launcher.signal_shutdown()
        icon.stop()

    def _build_program_menu(self) -> list:
        """Build restart sub-menu items for each managed process."""
        items = []
        for name in self.launcher.processes:
            items.append(
                pystray.MenuItem(
                    f"Restart {name}",
                    lambda icon, item, n=name: self._schedule(
                        self.launcher.restart(n)
                    ),
                )
            )
        return items

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("LaunchForge", None, enabled=False),
            pystray.Menu.SEPARATOR,
            *self._build_program_menu(),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Stop all", self._on_stop_all),
            pystray.MenuItem("Quit", self._on_quit),
        )

    def run(self) -> None:
        """Start the tray icon in the current thread (blocking)."""
        if not _TRAY_AVAILABLE:
            logger.warning(
                "System tray unavailable: install 'pystray' and 'Pillow' to enable."
            )
            return

        image = _make_icon_image()
        self._icon = pystray.Icon(
            "LaunchForge",
            image,
            "LaunchForge",
            menu=self._build_menu(),
        )
        self._icon.run()

    def stop(self) -> None:
        """Stop and remove the tray icon."""
        if self._icon is not None:
            with contextlib.suppress(Exception):
                self._icon.stop()


def start_tray_thread(launcher: Launcher, loop: asyncio.AbstractEventLoop) -> threading.Thread:
    """Launch the tray app in a background daemon thread.

    Returns the thread so callers can ``join()`` it on shutdown.
    """
    app = TrayApp(launcher, loop)
    thread = threading.Thread(target=app.run, daemon=True, name="launchforge-tray")
    thread.start()
    return thread
