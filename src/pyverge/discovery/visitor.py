"""Build-time registration visitor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pyverge.discovery.reflection import Reflector
from pyverge.discovery.types import (
    ReflectionReport,
    ReflectionStrategy,
    RegistrationContext,
    RegistrationPort,
    SourceDescriptor,
    SourceVisitor,
)


def _migration_count(registry: Any) -> int:
    return sum(len(registry.migrations(kind)) for kind in registry.kinds)


class RegistrationVisitor(SourceVisitor):
    """Dispatch source descriptors to reflection strategies."""

    def __init__(
        self,
        *,
        registrar: RegistrationPort,
        reflector: Reflector,
        context: RegistrationContext,
        strategies: Mapping[str, ReflectionStrategy],
    ) -> None:
        self._registrar = registrar
        self._reflector = reflector
        self._context = context
        self._strategies = dict(strategies)
        self._descriptors = 0
        self._models = 0
        self._migrations = 0
        self._skipped: list[str] = []

    def visit(self, descriptor: SourceDescriptor) -> None:
        strategy = self._strategies.get(descriptor.strategy)
        if strategy is None:
            self._skipped.append(descriptor.strategy)
            return
        before = len(self._registrar.registry.versions)
        migrations_before = _migration_count(self._registrar.registry)
        strategy.reflect(
            descriptor,
            registrar=self._registrar,
            reflector=self._reflector,
            context=self._context,
        )
        self._descriptors += 1
        self._models += max(len(self._registrar.registry.versions) - before, 0)
        self._migrations += max(
            _migration_count(self._registrar.registry) - migrations_before, 0
        )

    def report(self) -> ReflectionReport:
        return ReflectionReport(
            source_id=self._context.source_id,
            descriptors=self._descriptors,
            registered_models=self._models,
            registered_migrations=self._migrations,
            skipped=tuple(self._skipped),
        )


__all__ = ["RegistrationVisitor"]
