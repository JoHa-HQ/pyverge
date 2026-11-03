from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, runtime_checkable

from pyverge.core.types import MigrationFunc, VersionValue


@dataclass(frozen=True, slots=True)
class DiscoveredModel:
    """A model payload emitted by a source."""

    payload: Any
    source_id: str = ""


@dataclass(frozen=True, slots=True)
class DiscoveredMigration:
    """A migration registration emitted by a source."""

    key: Any
    func: MigrationFunc
    backward_compatible: bool = False
    discriminator: str = "default"
    source_id: str = ""


SourceDescriptor = DiscoveredModel | DiscoveredMigration


@runtime_checkable
class SourceVisitor(Protocol):
    """Receive descriptors from a source."""

    def visit(self, descriptor: SourceDescriptor) -> None: ...


@runtime_checkable
class SourcePort(Protocol):
    """Synchronous source of model and migration descriptors."""

    def accept(self, visitor: SourceVisitor) -> None: ...


@runtime_checkable
class AsyncSourcePort(Protocol):
    """Asynchronous source of model and migration descriptors."""

    async def accept(self, visitor: SourceVisitor) -> None: ...


@dataclass(frozen=True, slots=True)
class RegistrationContext:
    """Build-time discovery context."""

    source_id: str
    validate_references: bool = True


@dataclass(frozen=True, slots=True)
class DiscoveryReport:
    """Result of one collection or discovery pass."""

    source_id: str
    descriptors: int
    registered_models: int
    registered_migrations: int
    skipped: tuple[str, ...] = ()


@dataclass
class RegistrationCollector:
    """Collect descriptors and their registration intent."""

    source_id: str = ""
    descriptors: list[SourceDescriptor] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def visit(self, descriptor: SourceDescriptor) -> None:
        if isinstance(descriptor, (DiscoveredModel, DiscoveredMigration)):
            self.descriptors.append(descriptor)
        else:
            self.skipped.append(type(descriptor).__name__)


class DiscoveryService(Generic[VersionValue]):
    """Collect descriptors from a source and apply them to a manager."""

    def collect(
        self,
        source: SourcePort,
        *,
        context: RegistrationContext | None = None,
    ) -> RegistrationCollector:
        source_id = context.source_id if context else type(source).__name__
        collector = RegistrationCollector(source_id=source_id)
        source.accept(collector)
        return collector

    async def acollect(
        self,
        source: AsyncSourcePort,
        *,
        context: RegistrationContext | None = None,
    ) -> RegistrationCollector:
        source_id = context.source_id if context else type(source).__name__
        collector = RegistrationCollector(source_id=source_id)
        await source.accept(collector)
        return collector

    def report(self, collector: RegistrationCollector) -> DiscoveryReport:
        return DiscoveryReport(
            source_id=collector.source_id,
            descriptors=len(collector.descriptors),
            registered_models=0,
            registered_migrations=0,
            skipped=tuple(collector.skipped),
        )

    def apply(
        self,
        collector: RegistrationCollector,
        target: Any,
        *,
        context: RegistrationContext | None = None,
    ) -> DiscoveryReport:
        models = 0
        migrations = 0
        for descriptor in collector.descriptors:
            if isinstance(descriptor, DiscoveredModel):
                target.reconcile_model(descriptor.payload)
                models += 1
                continue
            target.store_migration(
                descriptor.key,
                descriptor.func,
                backward_compatible=descriptor.backward_compatible,
                discriminator=descriptor.discriminator,
            )
            migrations += 1
        if context is not None and context.validate_references:
            validate = getattr(target, "validate_graph", None)
            if validate is not None:
                validate()
        return DiscoveryReport(
            source_id=collector.source_id,
            descriptors=len(collector.descriptors),
            registered_models=models,
            registered_migrations=migrations,
            skipped=tuple(collector.skipped),
        )

    def discover(
        self,
        source: SourcePort,
        *,
        target: Any,
        context: RegistrationContext | None = None,
    ) -> DiscoveryReport:
        return self.apply(
            self.collect(source, context=context),
            target,
            context=context,
        )

    async def adiscover(
        self,
        source: AsyncSourcePort,
        *,
        target: Any,
        context: RegistrationContext | None = None,
    ) -> DiscoveryReport:
        return self.apply(
            await self.acollect(source, context=context),
            target,
            context=context,
        )


__all__ = [
    "AsyncSourcePort",
    "DiscoveredMigration",
    "DiscoveredModel",
    "DiscoveryReport",
    "DiscoveryService",
    "RegistrationCollector",
    "RegistrationContext",
    "SourceDescriptor",
    "SourcePort",
    "SourceVisitor",
]
