"""pyverge - versioned Pydantic models and schemas with migrations."""

from . import migration
from ._version import __version__

__all__ = [
    "__version__",
    "migration",
]
