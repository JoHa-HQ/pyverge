"""Build-discovery contracts."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pyverge.core.clock import Clock
from pyverge.core.types import MigrationFunc
from pyverge.reflection import Reflector
from pyverge.schemas.types import ModelAdapter
from pyverge.versioning import VersionNode


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    """One build-time fact emitted by a source."""

    strategy: str
    payload: Any
    source_id: str
    metadata: dict[str, Any]


@runtime_checkable
class SourceVisitor(Protocol):
    """Receive descriptors from a source."""

    def visit(self, descriptor: SourceDescriptor) -> None: ...


@runtime_checkable
class SourcePort(Protocol):
    """A traversable source of build descriptors."""

    def accept(self, visitor: SourceVisitor) -> None: ...


@dataclass(frozen=True, slots=True)
class RegistrationContext:
    """Context supplied to build-time visitors; never exposed to migrations."""

    source_id: str
    logger: Any
    clock: Clock
    validate_references: bool


@runtime_checkable
class RegistrationPort(Protocol):
    """Write surface needed by reflection strategies."""

    adapter: ModelAdapter
    registry: Any

    def store_model(self, version: VersionNode) -> VersionNode: ...
    def reconcile_model(self, version: VersionNode) -> VersionNode: ...
    def store_migration(
        self,
        key: Any,
        func: MigrationFunc,
        *,
        backward_compatible: bool = False,
    ) -> MigrationFunc: ...
    def propose_migration(self, source: VersionNode, target: VersionNode) -> Any: ...


@runtime_checkable
class DescriptorStrategy(Protocol):
    """Turn a source into descriptors."""

    def descriptors(self, source: SourcePort) -> Iterator[SourceDescriptor]: ...


@runtime_checkable
class ReflectionStrategy(Protocol):
    """Interpret one descriptor as registrations."""

    def reflect(
        self,
        descriptor: SourceDescriptor,
        *,
        registrar: RegistrationPort,
        reflector: Reflector,
        context: RegistrationContext,
    ) -> None: ...


__all__ = [
    "DescriptorStrategy",
    "ReflectionReport",
    "ReflectionStrategy",
    "RegistrationContext",
    "RegistrationPort",
    "SourceDescriptor",
    "SourcePort",
    "SourceVisitor",
]


@dataclass(frozen=True, slots=True)
class ReflectionReport:
    """What a reflection pass registered or skipped."""

    source_id: str
    descriptors: int
    registered_models: int
    registered_migrations: int
    skipped: tuple[str, ...]
