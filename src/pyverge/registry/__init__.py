"""Registry generic subdomain: types, in-memory store, explorer, and health."""

from .errors import (
    CatalogError,
    GraphLockedError,
    MigrationAlreadyRegisteredError,
    MigrationConflictError,
    MigrationNotFoundError,
    MigrationPathError,
    MigrationPathIntegrityError,
    MissingReferenceError,
    ModelAlreadyRegisteredError,
    ModelConflictError,
    ModelNotFoundError,
)
from .explorer import GraphExplorer
from .health import CatalogHealth, HealthReport
from .memory import InMemoryCatalog, Registry
from .types import (
    ContentHashLookup,
    GraphCatalog,
    MigrationWrite,
    ModelCatalog,
    ModelWrite,
    PathCatalog,
    RegistryPort,
)

__all__ = [
    "CatalogError",
    "CatalogHealth",
    "ContentHashLookup",
    "GraphCatalog",
    "GraphExplorer",
    "GraphLockedError",
    "HealthReport",
    "InMemoryCatalog",
    "MigrationAlreadyRegisteredError",
    "MigrationConflictError",
    "MigrationNotFoundError",
    "MigrationPathError",
    "MigrationPathIntegrityError",
    "MigrationWrite",
    "MissingReferenceError",
    "ModelAlreadyRegisteredError",
    "ModelCatalog",
    "ModelConflictError",
    "ModelNotFoundError",
    "ModelWrite",
    "PathCatalog",
    "Registry",
    "RegistryPort",
]
