"""Provider-specific model and migration ports.

*Model provider ports* know how a model class encodes its ``version`` and
``kind``: :class:`~pyverge.ports.pydantic.PydanticModelAdapter` and
:class:`~pyverge.ports.json_schema.JsonSchemaModelAdapter`.  The *migration
format* port owns RFC 6902 JSON Patch:
:class:`~pyverge.ports.json_patch.JsonPatch`.
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
