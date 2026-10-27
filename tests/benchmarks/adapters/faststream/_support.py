# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Support for driving async adapters under sync pytest-benchmark.

pytest-benchmark is sync-only. Benchmarks create one **persistent** event loop
(outside the timed region) and drive coroutines through :func:`run`, so the
measurement falls on the adapter, not on per-iteration loop startup.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

_T = TypeVar("_T")


def new_loop() -> asyncio.AbstractEventLoop:
    """Return a fresh event loop for a benchmark module."""
    return asyncio.new_event_loop()


def run(loop: asyncio.AbstractEventLoop, coro: Awaitable[_T]) -> _T:
    """Run *coro* to completion on the persistent *loop*."""
    return loop.run_until_complete(coro)


__all__ = ["new_loop", "run"]
