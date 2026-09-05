"""Provider-specific model adapters.

A :class:`ModelAdapter` is the only place allowed to know how a model
class encodes its ``version`` and ``kind``.  The rest of the migration
machinery works with :class:`Versionable` objects and never touches
provider-specific introspection APIs directly.
"""

from .pydantic import PydanticDiff, PydanticModelAdapter

__all__ = [
    "PydanticDiff",
    "PydanticModelAdapter",
]
