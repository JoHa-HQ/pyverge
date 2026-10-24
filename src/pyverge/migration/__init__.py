from pyverge.core import (
    MaxDepthExceededError,
    MigrationContext,
    Path,
    PayloadError,
    PayloadValidationError,
    get_at,
    set_at,
)
from pyverge.execution.errors import (
    AsyncExecutionRequired,
    ExecutionError,
    ExecutionModeError,
    SyncExecutionRequired,
)
from pyverge.migration.types import (
    Entry,
)
from pyverge.providers import (
    JsonataMigration,
    JsonataTransform,
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    PydanticDiff,
    PydanticModelAdapter,
)
from pyverge.reflection import (
    CallableDiffDiscovery,
    CompositeDiffDiscovery,
    DiffDiscovery,
    JsonPatchDiffDiscovery,
    JsonPatchRenderer,
)
from pyverge.registry import (
    Registry,
)
from pyverge.registry.errors import (
    CatalogError,
    MigrationAlreadyRegisteredError,
    MigrationNotFoundError,
    MigrationPathError,
    MigrationPathIntegrityError,
    MissingReferenceError,
    ModelAlreadyRegisteredError,
    ModelConflictError,
    ModelNotFoundError,
)
from pyverge.versioning import Diff, EdgeKey, VersionEdge, VersionKey, VersionNode
from pyverge.versioning.errors import MigrationApplicationError

from .engine import Engine
from .errors import BackwardCompatibilityError
from .graph import GraphBuilder, GraphEntry, MigrationGraph, MigrationPlan
from .policy import (
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from .registration import MigrationRegistrationService
from .walker import CompoundKeyWalker, PydanticWalker, Walker

__all__ = [
    "AsyncExecutionRequired",
    "BackwardCompatibilityError",
    "CallableDiffDiscovery",
    "CatalogError",
    "CompositeDiffDiscovery",
    "CompoundKeyWalker",
    "Diff",
    "DiffDiscovery",
    "EdgeKey",
    "Engine",
    "Entry",
    "ExecutionError",
    "ExecutionModeError",
    "GraphBuilder",
    "GraphEntry",
    "JsonPatchDiffDiscovery",
    "JsonPatchMigration",
    "JsonPatchRenderer",
    "JsonSchemaModelAdapter",
    "JsonataMigration",
    "JsonataTransform",
    "MaxDepthExceededError",
    "MigrationAlreadyRegisteredError",
    "MigrationApplicationError",
    "MigrationContext",
    "MigrationGraph",
    "MigrationNotFoundError",
    "MigrationPathError",
    "MigrationPathIntegrityError",
    "MigrationPlan",
    "MigrationRegistrationService",
    "MissingReferenceError",
    "ModelAlreadyRegisteredError",
    "ModelConflictError",
    "ModelNotFoundError",
    "Path",
    "PayloadError",
    "PayloadValidationError",
    "PydanticDiff",
    "PydanticModelAdapter",
    "PydanticWalker",
    "Registry",
    "SyncExecutionRequired",
    "VersionEdge",
    "VersionKey",
    "VersionNode",
    "Walker",
    "WalkerProtocol",
    "earliest_target_resolver",
    "fixed_target_resolver",
    "get_at",
    "latest_target_resolver",
    "multi_target_resolver",
    "set_at",
    "skip_target_resolver",
]
