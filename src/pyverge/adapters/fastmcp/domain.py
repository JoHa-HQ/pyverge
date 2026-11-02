"""Domain value objects for the FastMCP adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeAlias

from pyverge.manager.types import VersionRange

PolicyValue: TypeAlias = str | VersionRange
Policy: TypeAlias = PolicyValue | dict[str, PolicyValue]
EntranceKey: TypeAlias = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Entrance:
    """A versioned entry point into the application graph."""

    source: str
    kind: str
    version: str
    schema: dict[str, Any]
    handler: Callable[..., Any] | None
    policy: Policy
    explicit: bool

    @property
    def key(self) -> EntranceKey:
        """Return the graph identity of this entrance."""
        return (self.kind, self.version)


@dataclass(frozen=True, slots=True)
class VirtualComponent:
    """A graph version that needs a host primitive."""

    kind: str
    version: str
    schema: dict[str, Any]
    handler: Callable[..., Any]


__all__ = [
    "Entrance",
    "EntranceKey",
    "Policy",
    "PolicyValue",
    "VersionRange",
    "VirtualComponent",
]
