from __future__ import annotations

from dataclasses import dataclass
from functools import singledispatch
from typing import Any

from pyverge.discovery.types import RegistrationSink
from pyverge.migrations import MigrationSpec
from pyverge.versioning import EdgeKey


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    """One build-time fact emitted by a source."""

    payload: Any
    source_id: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelDescriptor(SourceDescriptor):
    """A model handle or pre-built version node."""


@dataclass(frozen=True, slots=True)
class MigrationDescriptor(SourceDescriptor):
    """A normalized migration specification."""


def is_registrable(descriptor: SourceDescriptor) -> bool:
    return isinstance(descriptor, (ModelDescriptor, MigrationDescriptor))


@singledispatch
def register_descriptor(
    descriptor: SourceDescriptor,
    sink: RegistrationSink,
) -> bool:
    """Apply one descriptor through the application registration port."""

    return False


@register_descriptor.register
def _register_model_descriptor(
    descriptor: ModelDescriptor,
    sink: RegistrationSink,
) -> bool:
    payload = descriptor.payload
    if isinstance(payload, (list, tuple, set, frozenset)):
        for item in payload:
            register_descriptor(
                ModelDescriptor(item, descriptor.source_id, descriptor.metadata),
                sink,
            )
        return True
    sink.reconcile_model(payload)
    return True


@register_descriptor.register
def _register_migration_descriptor(
    descriptor: MigrationDescriptor,
    sink: RegistrationSink,
) -> bool:
    payload = descriptor.payload
    if not isinstance(payload, MigrationSpec):
        raise TypeError("migration descriptor payload must be a MigrationSpec")
    sink.store_migration(
        EdgeKey.from_pair(*payload.pair),
        payload.func,
        backward_compatible=payload.backward_compatible,
    )
    return True


__all__ = [
    "MigrationDescriptor",
    "ModelDescriptor",
    "SourceDescriptor",
    "is_registrable",
    "register_descriptor",
]
