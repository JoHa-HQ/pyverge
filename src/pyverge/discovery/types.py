from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    TypeAlias,
    Union,
    runtime_checkable,
)

from pyverge.core.clock import Clock
from pyverge.core.types import (
    MigrationFunc,
    MigrationKeyInput,
    NodeInput,
)
from pyverge.migrations import MigrationSpec
from pyverge.versioning import EdgeEntry

if TYPE_CHECKING:
    from pyverge.discovery.descriptors import SourceDescriptor
    from pyverge.migrations import JsonataMigration, JsonPatchMigration

#: Inputs accepted by manager migration registration.
MigrationSource: TypeAlias = Union[
    MigrationFunc,
    MigrationSpec,
    "JsonPatchMigration",
    "JsonataMigration",
]


@runtime_checkable
class RegistrationSink(Protocol):
    """Application-facing registration surface used by discovery adapters."""

    def store_model(self, payload: NodeInput) -> Any: ...

    def reconcile_model(self, payload: NodeInput) -> Any: ...

    def store_migration(
        self,
        key: MigrationKeyInput,
        source: MigrationSource,
        *,
        backward_compatible: bool = False,
        migration_id: str | None = None,
    ) -> EdgeEntry: ...


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
    "MigrationSource",
    "ReflectionReport",
    "RegistrationContext",
    "RegistrationSink",
    "SourcePort",
    "SourceVisitor",
]
