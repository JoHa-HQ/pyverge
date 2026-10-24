"""Model descriptor reflection."""

from __future__ import annotations

from pyverge.discovery.reflection import Reflector
from pyverge.discovery.types import (
    RegistrationContext,
    RegistrationPort,
    SourceDescriptor,
)
from pyverge.versioning import VersionNode


class ModelSchemaStrategy:
    """Register model handles or pre-built version nodes."""

    def reflect(
        self,
        descriptor: SourceDescriptor,
        *,
        registrar: RegistrationPort,
        reflector: Reflector,
        context: RegistrationContext,
    ) -> None:
        payload = descriptor.payload
        if isinstance(payload, VersionNode):
            registrar.reconcile_model(payload)
            return
        if isinstance(payload, (list, tuple, set, frozenset)):
            for item in payload:
                self.reflect(
                    SourceDescriptor(
                        descriptor.strategy,
                        item,
                        descriptor.source_id,
                        descriptor.metadata,
                    ),
                    registrar=registrar,
                    reflector=reflector,
                    context=context,
                )
            return
        registrar.reconcile_model(registrar.adapter.versionable(payload))


__all__ = ["ModelSchemaStrategy"]
