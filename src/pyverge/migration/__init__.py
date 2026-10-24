from pyverge.core import (
    MaxDepthExceededError,
    MigrationContext,
    PayloadError,
    PayloadValidationError,
)
from pyverge.discovery.reflection import (
    CallableDiffDiscovery,
    CompositeDiffDiscovery,
    DiffDiscovery,
    JsonPatchDiffDiscovery,
    JsonPatchRenderer,
)
from pyverge.execution.errors import (
    AsyncExecutionRequired,
    ExecutionError,
    ExecutionModeError,
    SyncExecutionRequired,
)
from pyverge.execution.targets import (
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from pyverge.providers import (
    JsonataMigration,
    JsonataTransform,
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    PydanticDiff,
    PydanticModelAdapter,
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
from .registration import MigrationRegistrationService

__all__ = [
    "AsyncExecutionRequired",
    "BackwardCompatibilityError",
    "CallableDiffDiscovery",
    "CatalogError",
    "CompositeDiffDiscovery",
    "Diff",
    "DiffDiscovery",
    "EdgeKey",
    "Engine",
    "ExecutionError",
    "ExecutionModeError",
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
    "MigrationNotFoundError",
    "MigrationPathError",
    "MigrationPathIntegrityError",
    "MigrationRegistrationService",
    "MissingReferenceError",
    "ModelAlreadyRegisteredError",
    "ModelConflictError",
    "ModelNotFoundError",
    "PayloadError",
    "PayloadValidationError",
    "PydanticDiff",
    "PydanticModelAdapter",
    "Registry",
    "SyncExecutionRequired",
    "VersionEdge",
    "VersionKey",
    "VersionNode",
    "WalkerProtocol",
    "earliest_target_resolver",
    "fixed_target_resolver",
    "latest_target_resolver",
    "multi_target_resolver",
    "skip_target_resolver",
]
