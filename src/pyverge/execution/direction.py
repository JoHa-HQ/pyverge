from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pyverge.core.types import MigrationDirectionStrategy, VersionValue
from pyverge.versioning import VersionNode


@runtime_checkable
class DirectionPolicy(Protocol):
    """Allow or reject a source -> target direction."""

    def allows(
        self, source: VersionNode[VersionValue], target: VersionNode[VersionValue]
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class AnyDirection:
    """Allow every direction."""

    def allows(
        self, source: VersionNode[VersionValue], target: VersionNode[VersionValue]
    ) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class ForwardDirection:
    """Allow only ascending versions."""

    def allows(
        self, source: VersionNode[VersionValue], target: VersionNode[VersionValue]
    ) -> bool:
        return source < target


@dataclass(frozen=True, slots=True)
class BackwardDirection:
    """Allow only descending versions."""

    def allows(
        self, source: VersionNode[VersionValue], target: VersionNode[VersionValue]
    ) -> bool:
        return source > target


def direction_policy(strategy: MigrationDirectionStrategy) -> DirectionPolicy:
    match strategy:
        case "any":
            return AnyDirection()
        case "forward":
            return ForwardDirection()
        case "backward":
            return BackwardDirection()
        case _:
            raise ValueError(f"Unknown direction strategy: {strategy!r}")


__all__ = [
    "AnyDirection",
    "BackwardDirection",
    "DirectionPolicy",
    "ForwardDirection",
    "direction_policy",
]
