"""Build-time descriptors and their registration commands."""

from __future__ import annotations

from dataclasses import dataclass
from functools import singledispatch
from typing import Any

from pyverge.discovery.commands import (
    MigrationSpec,
    ModelRegistrationMode,
    RegisterMigration,
    RegisterModel,
)
from pyverge.discovery.types import RegistrationCommand


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


@singledispatch
def descriptor_commands(
    descriptor: SourceDescriptor,
) -> tuple[RegistrationCommand, ...]:
    """Return no commands for descriptors without a handler."""
    return ()


@descriptor_commands.register
def _model_commands(
    descriptor: ModelDescriptor,
) -> tuple[RegistrationCommand, ...]:
    payload = descriptor.payload
    if isinstance(payload, (list, tuple, set, frozenset)):
        commands: list[RegistrationCommand] = []
        for item in payload:
            commands.extend(
                descriptor_commands(
                    ModelDescriptor(item, descriptor.source_id, descriptor.metadata)
                )
            )
        return tuple(commands)
    return (RegisterModel(payload, ModelRegistrationMode.RECONCILE),)


@descriptor_commands.register
def _migration_commands(
    descriptor: MigrationDescriptor,
) -> tuple[RegistrationCommand, ...]:
    payload = descriptor.payload
    if not isinstance(payload, MigrationSpec):
        raise TypeError("migration descriptor payload must be a MigrationSpec")
    return (RegisterMigration(payload),)


__all__ = [
    "MigrationDescriptor",
    "ModelDescriptor",
    "SourceDescriptor",
    "descriptor_commands",
]
