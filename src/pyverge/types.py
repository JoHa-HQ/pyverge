"""Backward-compatibility re-export shim.

The monolithic core type module was split by concern.  Type surface now lives
in per-package ``types.py`` modules; this shim re-exports the symbols from
their new homes so internal importers keep working for one release.  Provider
model TypeVars and ``ModelBase`` are **not** re-exported: they were removed
from the public core surface (provider type parameters now live in
:mod:`pyverge.schemas.types`).
"""

from __future__ import annotations

from pyverge.core.types import (
    MIGRATION_PAIR_LEN,
    Attachable,
    DirectionViolationStrategy,
    ExtraFieldStrategy,
    JsonPrimities,
    JsonSchema,
    JsonSchemaDefinitions,
    JsonSchemaGenerator,
    JsonSchemaMode,
    JsonValue,
    ManagerKey,
    ManagerMigrationKey,
    MigrationDirectionStrategy,
    MigrationFunc,
    MigrationKeyInput,
    MissingFieldStrategy,
    ModelData,
    ModelHandle,
    ModelKey,
    ModelKind,
    ModelPair,
    ModelVersionKey,
    RenderingFormat,
    SchemaTransformer,
    TargetResolver,
    TargetStrategy,
    ValidationMode,
    VersionMissingStrategy,
    VersionValue,
    VersionValue_co,
)
from pyverge.execution.types import Entry, EntryExtractor
from pyverge.manager.types import (
    ManagerClassState,
    ManagerInstanceState,
    ResolverFactory,
    TargetPolicy,
    TargetSpec,
)
from pyverge.schemas.types import (
    ModelAdapter,
)
from pyverge.versioning import (
    Comparable,
    EdgeKey,
    LookupKey,
    Migratable,
    MigrationHookMap,
    MigrationKey,
    Orderable,
    Transitional,
    Versionable,
    VersionEdge,
    VersionKey,
    VersionNode,
    VersionPair,
)

__all__ = [
    "MIGRATION_PAIR_LEN",
    "Attachable",
    "Comparable",
    "DirectionViolationStrategy",
    "EdgeKey",
    "Entry",
    "EntryExtractor",
    "ExtraFieldStrategy",
    "JsonPrimities",
    "JsonSchema",
    "JsonSchemaDefinitions",
    "JsonSchemaGenerator",
    "JsonSchemaMode",
    "JsonValue",
    "LookupKey",
    "ManagerClassState",
    "ManagerInstanceState",
    "ManagerKey",
    "ManagerMigrationKey",
    "Migratable",
    "MigrationDirectionStrategy",
    "MigrationFunc",
    "MigrationHookMap",
    "MigrationKey",
    "MigrationKeyInput",
    "MissingFieldStrategy",
    "ModelAdapter",
    "ModelData",
    "ModelHandle",
    "ModelKey",
    "ModelKind",
    "ModelPair",
    "ModelVersionKey",
    "Orderable",
    "RenderingFormat",
    "ResolverFactory",
    "SchemaTransformer",
    "TargetPolicy",
    "TargetResolver",
    "TargetSpec",
    "TargetStrategy",
    "Transitional",
    "ValidationMode",
    "VersionEdge",
    "VersionKey",
    "VersionMissingStrategy",
    "VersionNode",
    "VersionPair",
    "VersionValue",
    "VersionValue_co",
    "Versionable",
]
