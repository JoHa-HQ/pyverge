"""pydantic-migrator - versioned Pydantic models and schemas with migrations."""

from . import migration
from ._version import __version__
from .coordination import Coordinator
from .models import SchemaConfig
from .strategies import BatchStrategy, ParallelStrategy, StreamingStrategy

__all__ = [
    "BatchStrategy",
    "Coordinator",
    "ParallelStrategy",
    "SchemaConfig",
    "StreamingStrategy",
    "__version__",
    "migration",
]
