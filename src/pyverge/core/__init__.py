"""Shared foundational components for pyverge.

This package holds the provider-agnostic building blocks used by the
``registry``, ``executor``, ``engine`` and ``migration`` packages.  It has no
dependencies on the rest of the library — everything else depends on it.
"""

from .exceptions import (
    DiscoveryError,
    DiscoveryValidationError,
    EngineError,
    MaxDepthExceededError,
    MigrationAlreadyRegisteredError,
    MigrationError,
    MigrationMissingFieldError,
    MigrationNotFoundError,
    MigrationPathIntegrityError,
    ModelAlreadyRegisteredError,
    ModelNotFoundError,
    RegistryError,
    VersionedModelError,
)
from .hooks import MigrationHook, OTELHook
from .path import Path, get_at, set_at
from .render import JsonPatchRender
from .settings import DiscoverySettings, MigrationSettings, VersioningSettings
from .steps import ExplicitStep
from .versioning import SentinelEdge, VersionEdge, VersionNode

__all__ = [
    "DiscoveryError",
    "DiscoverySettings",
    "DiscoveryValidationError",
    "EngineError",
    "ExplicitStep",
    "JsonPatchRender",
    "MaxDepthExceededError",
    "MigrationAlreadyRegisteredError",
    "MigrationError",
    "MigrationHook",
    "MigrationMissingFieldError",
    "MigrationNotFoundError",
    "MigrationPathIntegrityError",
    "MigrationSettings",
    "ModelAlreadyRegisteredError",
    "ModelNotFoundError",
    "OTELHook",
    "Path",
    "RegistryError",
    "SentinelEdge",
    "VersionEdge",
    "VersionNode",
    "VersionedModelError",
    "VersioningSettings",
    "get_at",
    "set_at",
]
