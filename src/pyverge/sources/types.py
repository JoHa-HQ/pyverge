"""Optional integration lifecycle contracts.

Source descriptor/traversal contracts live in :mod:`pyverge.discovery.types`;
integration sources implement them above the discovery build context.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pyverge.discovery.types import SourceDescriptor, SourcePort, SourceVisitor


@runtime_checkable
class LifecyclePort(Protocol):
    """Optional host lifecycle seam owned by the application."""

    def start(self) -> None: ...
    def stop(self) -> None: ...


__all__ = [
    "LifecyclePort",
    "SourceDescriptor",
    "SourcePort",
    "SourceVisitor",
]
