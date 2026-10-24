"""Composite descriptor reflection."""

from __future__ import annotations

from collections.abc import Mapping

from pyverge.discovery.strategies.migrations import MigrationStrategy
from pyverge.discovery.strategies.models import ModelSchemaStrategy
from pyverge.discovery.types import (
    RegistrationContext,
    RegistrationPort,
    SourceDescriptor,
)
from pyverge.reflection import Reflector


class CompositeStrategy:
    """Handle a mapping of model and migration descriptors."""

    def __init__(self) -> None:
        self._models = ModelSchemaStrategy()
        self._migrations = MigrationStrategy()

    def reflect(
        self,
        descriptor: SourceDescriptor,
        *,
        registrar: RegistrationPort,
        reflector: Reflector,
        context: RegistrationContext,
    ) -> None:
        payload = descriptor.payload
        if not isinstance(payload, Mapping):
            raise TypeError("composite descriptor payload must be a mapping")
        for item in payload.get("models", ()):  # type: ignore[union-attr]
            self._models.reflect(
                SourceDescriptor("model", item, descriptor.source_id, {}),
                registrar=registrar,
                reflector=reflector,
                context=context,
            )
        for item in payload.get("migrations", ()):  # type: ignore[union-attr]
            self._migrations.reflect(
                SourceDescriptor("migration", item, descriptor.source_id, {}),
                registrar=registrar,
                reflector=reflector,
                context=context,
            )


__all__ = ["CompositeStrategy"]
