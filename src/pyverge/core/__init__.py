"""Core shared kernel: primitives, context contract, clock, ids, errors.

Version graph types and protocols live in :mod:`pyverge.versioning`.
"""

from .clock import Clock, SystemClock
from .context import EMPTY_CONTEXT, MigrationContext
from .errors import (
    MaxDepthExceededError,
    PayloadError,
    PayloadValidationError,
    PyvergeError,
)
from .ids import IdFactory, UuidIdFactory
from .types import (
    MIGRATION_PAIR_LEN,
    Attachable,
    DirectionViolationStrategy,
    ManagerKey,
    ManagerMigrationKey,
    MigrationDirectionStrategy,
    MigrationFunc,
    MigrationKeyInput,
    ModelData,
    ModelHandle,
    ModelKey,
    ModelKind,
    ModelPair,
    ModelVersionKey,
    TargetResolver,
    TargetStrategy,
    ValidationMode,
    VersionMissingStrategy,
    VersionValue,
    VersionValue_co,
)

__all__ = [
    "EMPTY_CONTEXT",
    "MIGRATION_PAIR_LEN",
    "Attachable",
    "Clock",
    "DirectionViolationStrategy",
    "IdFactory",
    "ManagerKey",
    "ManagerMigrationKey",
    "MaxDepthExceededError",
    "MigrationContext",
    "MigrationDirectionStrategy",
    "MigrationFunc",
    "MigrationKeyInput",
    "ModelData",
    "ModelHandle",
    "ModelKey",
    "ModelKind",
    "ModelPair",
    "ModelVersionKey",
    "PayloadError",
    "PayloadValidationError",
    "PyvergeError",
    "SystemClock",
    "TargetResolver",
    "TargetStrategy",
    "UuidIdFactory",
    "ValidationMode",
    "VersionMissingStrategy",
    "VersionValue",
    "VersionValue_co",
]
