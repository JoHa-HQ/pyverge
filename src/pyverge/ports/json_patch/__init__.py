"""RFC 6902 JSON Patch migration format.

The executable :class:`JsonPatch` (:mod:`.patch`) and the declarative
:class:`JsonPatchMigration` spec wrapper (:mod:`.migration`).  Discovery
consumes a :class:`JsonPatch` directly to build a :class:`Diff`.
"""

from .migration import JsonPatchMigration
from .patch import (
    CoerceOperation,
    JsonPatch,
    MapOperation,
    SetDefaultOperation,
    SplitOperation,
)
from .pointer import Pointer

__all__ = [
    "CoerceOperation",
    "JsonPatch",
    "JsonPatchMigration",
    "MapOperation",
    "Pointer",
    "SetDefaultOperation",
    "SplitOperation",
]
