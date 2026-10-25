from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic

from pyverge.core.clock import Clock, SystemClock
from pyverge.core.types import VersionValue
from pyverge.discovery import (
    ReflectionReport,
    RegistrationCollector,
    RegistrationContext,
)
from pyverge.discovery.types import AsyncSourcePort, SourcePort
from pyverge.registry.errors import GraphLockedError

if TYPE_CHECKING:
    from pyverge.manager.manager import Manager


class ReflectionMixin(Generic[VersionValue]):
    """Drive source descriptors into the class-level build engine."""

    @classmethod
    def _collector(
        cls: type[Manager[VersionValue]],
        source: Any,
        *,
        context: RegistrationContext | None,
        logger: Any,
        clock: Clock | None,
    ) -> tuple[RegistrationContext, RegistrationCollector]:
        if getattr(cls, "_reflection_locked", False):
            raise GraphLockedError(
                cls._default_engine.registry.name,
                "reflect after manager instantiation",
            )
        registration_context = context or RegistrationContext(
            source_id=type(source).__name__,
            logger=logger,
            clock=clock or SystemClock(),
            validate_references=True,
        )
        return registration_context, RegistrationCollector()

    @classmethod
    def _report(
        cls: type[Manager[VersionValue]],
        registration_context: RegistrationContext,
        collector: RegistrationCollector,
        *,
        models_before: int,
        migrations_before: int,
    ) -> ReflectionReport:
        engine = cls._default_engine
        if registration_context.validate_references:
            engine.validate()
        migrations_after = sum(
            len(engine.registry.migrations(kind)) for kind in engine.registry.kinds
        )
        return ReflectionReport(
            source_id=registration_context.source_id,
            descriptors=collector.descriptors,
            registered_models=max(len(engine.registry.versions) - models_before, 0),
            registered_migrations=max(migrations_after - migrations_before, 0),
            skipped=tuple(collector.skipped),
        )

    @classmethod
    def reflect(
        cls: type[Manager[VersionValue]],
        source: SourcePort,
        *,
        context: RegistrationContext | None = None,
        logger: Any = None,
        clock: Clock | None = None,
    ) -> ReflectionReport:
        registration_context, collector = cls._collector(
            source,
            context=context,
            logger=logger,
            clock=clock,
        )
        engine = cls._default_engine
        models_before = len(engine.registry.versions)
        migrations_before = sum(
            len(engine.registry.migrations(kind)) for kind in engine.registry.kinds
        )
        source.accept(collector)
        for command in collector.commands:
            engine.register(command)
        return cls._report(
            registration_context,
            collector,
            models_before=models_before,
            migrations_before=migrations_before,
        )

    @classmethod
    async def areflect(
        cls: type[Manager[VersionValue]],
        source: AsyncSourcePort,
        *,
        context: RegistrationContext | None = None,
        logger: Any = None,
        clock: Clock | None = None,
    ) -> ReflectionReport:
        registration_context, collector = cls._collector(
            source,
            context=context,
            logger=logger,
            clock=clock,
        )
        engine = cls._default_engine
        models_before = len(engine.registry.versions)
        migrations_before = sum(
            len(engine.registry.migrations(kind)) for kind in engine.registry.kinds
        )
        await source.accept(collector)
        for command in collector.commands:
            engine.register(command)
        return cls._report(
            registration_context,
            collector,
            models_before=models_before,
            migrations_before=migrations_before,
        )


__all__ = ["ReflectionMixin"]
