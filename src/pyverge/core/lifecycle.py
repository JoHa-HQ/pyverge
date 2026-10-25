from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LifecyclePort(Protocol):
    """Optional host lifecycle seam owned by the application."""

    def start(self) -> None: ...
    def stop(self) -> None: ...


__all__ = ["LifecyclePort"]
