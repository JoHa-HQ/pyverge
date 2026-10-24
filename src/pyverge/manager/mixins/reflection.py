"""Build-time source reflection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Generic

from pyverge.core.clock import Clock, SystemClock
from pyverge.core.types import VersionValue
from pyverge.discovery import (
    CompositeStrategy,
    MigrationStrategy,
    ModelSchemaStrategy,
    ReflectionReport,
    ReflectionStrategy,
    RegistrationContext,
    RegistrationVisitor,
    RoutesStrategy,
    TablesStrategy,
    TopicsStrategy,
)
from pyverge.discovery.types import SourcePort
from pyverge.registry.errors import GraphLockedError

if TYPE_CHECKING:
    from pyverge.manager.manager import Manager


def _default_strategies() -> dict[str, ReflectionStrategy]:
    return {
        "model": ModelSchemaStrategy(),
        "model_schema": ModelSchemaStrategy(),
        "migration": MigrationStrategy(),
        "route": RoutesStrategy(),
        "topic": TopicsStrategy(),
        "table": TablesStrategy(),
        "composite": CompositeStrategy(),
    }


class ReflectionMixin(Generic[VersionValue]):
    """Drive source descriptors into the class-level build engine."""

    @classmethod
    def reflect(
        cls: type[Manager[VersionValue]],
        source: SourcePort,
        *,
        strategies: Mapping[str, ReflectionStrategy] | None = None,
        context: RegistrationContext | None = None,
        logger: Any = None,
        clock: Clock | None = None,
    ) -> ReflectionReport:
        """Reflect *source* into the build registry, then validate references."""
        if getattr(cls, "_reflection_locked", False):
            raise GraphLockedError(
                cls._default_engine.registry.name,
                "reflect after manager instantiation",
            )
        engine = cls._default_engine
        registration_context = context or RegistrationContext(
            source_id=type(source).__name__,
            logger=logger,
            clock=clock or SystemClock(),
            validate_references=True,
        )
        visitor = RegistrationVisitor(
            registrar=engine,
            reflector=engine.reflector,
            context=registration_context,
            strategies=strategies or _default_strategies(),
        )
        source.accept(visitor)
        if registration_context.validate_references:
            engine.validate()
        return visitor.report()


__all__ = ["ReflectionMixin"]
