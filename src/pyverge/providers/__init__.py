"""Deprecated compatibility surface.

Use :mod:`pyverge.schemas` for model/schema providers and
:mod:`pyverge.migrations` for migration backends.
"""

from pyverge.migrations import (
    CoerceOperation,
    DefaultMigrationIdentityResolver,
    JsonataMigration,
    JsonataTransform,
    JsonPatch,
    JsonPatchMigration,
    JsonPatchMigrationBackend,
    MapOperation,
    MigrationIdentityResolver,
    Pointer,
    SetDefaultOperation,
    SplitOperation,
)
from pyverge.schemas import (
    AbstractModelAdapter,
    DataclassModelAdapter,
    JsonSchemaModelAdapter,
    ModelAdapter,
    ModelIdentity,
    ModelMaterializer,
    ProviderCapabilityError,
    PydanticDiff,
    PydanticModelAdapter,
)

__all__ = [
    "AbstractModelAdapter",
    "CoerceOperation",
    "DataclassModelAdapter",
    "DefaultMigrationIdentityResolver",
    "JsonPatch",
    "JsonPatchMigration",
    "JsonPatchMigrationBackend",
    "JsonSchemaModelAdapter",
    "JsonataMigration",
    "JsonataTransform",
    "MapOperation",
    "MigrationIdentityResolver",
    "ModelAdapter",
    "ModelIdentity",
    "ModelMaterializer",
    "Pointer",
    "ProviderCapabilityError",
    "PydanticDiff",
    "PydanticModelAdapter",
    "SetDefaultOperation",
    "SplitOperation",
]
