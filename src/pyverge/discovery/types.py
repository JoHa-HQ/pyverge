from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, runtime_checkable

from pyverge.core.clock import Clock
from pyverge.discovery.commands import RegisterMigration, RegisterModel

if TYPE_CHECKING:
    from pyverge.discovery.descriptors import SourceDescriptor

RegistrationCommand: TypeAlias = RegisterModel | RegisterMigration


@runtime_checkable
class SourceVisitor(Protocol):
    """Receive descriptors from a source."""

    def visit(self, descriptor: SourceDescriptor) -> None: ...


@runtime_checkable
class SourcePort(Protocol):
    """A synchronous source of build descriptors."""

    def accept(self, visitor: SourceVisitor) -> None: ...


class AsyncSourcePort(Protocol):
    """An asynchronous source of build descriptors."""

    async def accept(self, visitor: SourceVisitor) -> None: ...


@dataclass(frozen=True, slots=True)
class RegistrationContext:
    """Context supplied to build-time visitors; never exposed to migrations."""

    source_id: str
    logger: Any
    clock: Clock
    validate_references: bool


@runtime_checkable
class DescriptorStrategy(Protocol):
    """Turn a source into descriptors."""

    def descriptors(self, source: SourcePort) -> Iterator[SourceDescriptor]: ...


@dataclass(frozen=True, slots=True)
class ReflectionReport:
    """What a reflection pass registered or skipped."""

    source_id: str
    descriptors: int
    registered_models: int
    registered_migrations: int
    skipped: tuple[str, ...]


__all__ = [
    "AsyncSourcePort",
    "DescriptorStrategy",
    "ReflectionReport",
    "RegistrationCommand",
    "RegistrationContext",
    "SourcePort",
    "SourceVisitor",
]
