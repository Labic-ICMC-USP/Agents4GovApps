"""Reusable `__event_emitter__` callbacks for `collect_general_news` /
`collect_by_sources`.

The library emits status events (`{"type": "status", "data": {"description": str,
"done": bool}}`) once per window during collection. Without an emitter the
caller only sees one summary log per query, which can look stuck on long
periods. These helpers wire those events into common sinks (stdlib logging,
plain stdout) without requiring callers to write boilerplate async lambdas.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

EventCallback = Callable[[dict], Awaitable[None]]


def console_emitter(
    logger: logging.Logger | None = None,
    level: int = logging.INFO,
    prefix: str = "",
) -> EventCallback:
    """Returns an async callback that forwards each event's description to a logger.

    Args:
        logger: Target logger. Defaults to the root logger.
        level:  Log level for emitted lines (default INFO).
        prefix: String prepended to every line, e.g. ``"q=1/81 :: "``.
    """
    target = logger or logging.getLogger()

    async def emit(event):
        if not isinstance(event, dict):
            return
        data = event.get("data") or {}
        desc = data.get("description")
        if not desc:
            return
        target.log(level, "%s%s", prefix, desc)

    return emit


def stdout_emitter(prefix: str = "") -> EventCallback:
    """Returns an async callback that prints each event's description to stdout."""

    async def emit(event):
        if not isinstance(event, dict):
            return
        data = event.get("data") or {}
        desc = data.get("description")
        if desc:
            print(f"{prefix}{desc}", flush=True)

    return emit
