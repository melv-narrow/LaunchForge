"""Desktop notifications via plyer (optional dependency)."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

try:
    from plyer import notification as _plyer_notification  # type: ignore[import-untyped]
    _PLYER_AVAILABLE = True
except ImportError:
    _PLYER_AVAILABLE = False


async def send_notification(title: str, message: str, timeout: int = 10) -> None:
    """Send a desktop notification asynchronously.

    Falls back to a log warning when ``plyer`` is not installed.

    Args:
        title: Notification title.
        message: Notification body text.
        timeout: How long (seconds) the notification should stay visible.
    """
    if not _PLYER_AVAILABLE:
        logger.warning("Desktop notification (plyer not installed): %s — %s", title, message)
        return

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: _plyer_notification.notify(
            title=title,
            message=message,
            app_name="LaunchForge",
            timeout=timeout,
        ),
    )
