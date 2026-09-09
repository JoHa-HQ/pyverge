"""Provider-specific model adapters and migration formats.

*Model provider adapters* know how a model class encodes its ``version`` and
``kind``: :class:`~pyverge.adapters.pydantic.PydanticModelAdapter` and
:class:`~pyverge.adapters.json_schema.JsonSchemaModelAdapter`.  The *migration
format* adapter owns RFC 6902 JSON Patch:
:class:`~pyverge.adapters.json_patch.JsonPatch`.
"""

from .json_patch import (
    CoerceOperation,
    JsonPatch,
    JsonPatchMigration,
    MapOperation,
    Pointer,
    SetDefaultOperation,
    SplitOperation,
)
from .json_schema import JsonSchemaModelAdapter
from .pydantic import PydanticDiff, PydanticModelAdapter

__all__ = [
    "CoerceOperation",
    "JsonPatch",
    "JsonPatchMigration",
    "JsonSchemaModelAdapter",
    "MapOperation",
    "Pointer",
    "PydanticDiff",
    "PydanticModelAdapter",
    "SetDefaultOperation",
    "SplitOperation",
]
