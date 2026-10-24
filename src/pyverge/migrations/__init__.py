"""Migration backends: callable identity, JSON Patch, JSONata."""

from .identity import DefaultMigrationIdentityResolver, MigrationIdentityResolver
from .json_patch import (
    CoerceOperation,
    JsonPatch,
    JsonPatchMigration,
    JsonPatchMigrationBackend,
    MapOperation,
    Pointer,
    SetDefaultOperation,
    SplitOperation,
)
from .jsonata import JsonataMigration, JsonataTransform

__all__ = [
    "CoerceOperation",
    "DefaultMigrationIdentityResolver",
    "JsonPatch",
    "JsonPatchMigration",
    "JsonPatchMigrationBackend",
    "JsonataMigration",
    "JsonataTransform",
    "MapOperation",
    "MigrationIdentityResolver",
    "Pointer",
    "SetDefaultOperation",
    "SplitOperation",
]
