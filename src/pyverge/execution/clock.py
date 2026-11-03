from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Time source injected into services and runtime contexts."""

    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class SystemClock:
    """Default wall-clock implementation."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()


__all__ = ["Clock", "SystemClock"]
