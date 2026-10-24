"""Clock port for deterministic time in domain services."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Time source injected into services and runtime contexts."""

    def now(self) -> datetime:
        """Current wall-clock time (timezone-aware)."""
        ...

    def monotonic(self) -> float:
        """Monotonic seconds for durations."""
        ...


class SystemClock:
    """Default wall-clock implementation."""

    def now(self) -> datetime:
        """Return timezone-aware UTC now."""
        return datetime.now(UTC)

    def monotonic(self) -> float:
        """Return the process monotonic clock."""
        return time.monotonic()


__all__ = ["Clock", "SystemClock"]
