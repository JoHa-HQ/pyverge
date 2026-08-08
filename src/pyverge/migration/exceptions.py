from collections.abc import Sequence
from typing import Any, Self

from .types import (
    MigrationKey,
    ModelBase,
    ModelVersionKey,
    VersionValue,
)

# Length of an endpoint-pair key, e.g. ``(source, target)``.
_ENDPOINT_PAIR = 2


class RegistryError(Exception):
    """Raised when a registry error occurs."""

    def __init__(
        self: Self,
        registry_name: str,
        message: str,
    ) -> None:
        """Initializes RegistryError."""
        self.registry_name = registry_name
        super().__init__(message)


class InvalidVersionError(RegistryError):
    """Raised when a version string cannot be parsed."""

    def __init__(
        self: Self,
        registry_name: str,
        version: VersionValue,
        reason: str | None = None,
    ) -> None:
        """Initializes InvalidVersionError."""
        self.version = version
        msg = f"Invalid version string: '{version}'"
        if reason:
            msg += f"\n{reason}"
        super().__init__(registry_name, msg)


class VersionedModelError(RegistryError):
    """Base exception for all versioned model errors."""

    def __init__(
        self: Self,
        registry_name: str,
        version: ModelVersionKey,
        message: str,
    ) -> None:
        """Initializes VersionedModelError."""
        self.version = version
        self.message = message
        super().__init__(registry_name, f"Registry error: {registry_name} - {message}")


class ModelNotFoundError(RegistryError):
    """Raised when a model or version cannot be found in the registry."""

    def __init__(
        self: Self,
        registry_name: str,
        key: ModelVersionKey | type[ModelBase],
    ) -> None:
        """Initializes ModelNotFoundError."""
        self.key = key
        super().__init__(registry_name, f"Model not found: {key}")


class ModelAlreadyRegisteredError(RegistryError):
    """Raised when a model is already registered."""

    def __init__(
        self: Self,
        registry_name: str,
        version: ModelVersionKey,
    ) -> None:
        """Initializes ModelAlreadyRegisteredError."""
        self.version = version
        msg = f"Model at version '{version}' is already registered"
        super().__init__(registry_name, msg)


class MigrationPathNotFoundError(RegistryError):
    """Raised when a migration path cannot be found."""

    def __init__(
        self: Self,
        registry_name: str,
        from_version: MigrationKey,
        to_version: MigrationKey,
    ) -> None:
        """Initializes MigrationPathNotFoundError."""
        self.from_version = from_version
        self.to_version = to_version
        msg = f"Migration path not found: {from_version} → {to_version}"
        super().__init__(registry_name, msg)


class MigrationNotFoundError(RegistryError):
    """Raised when a migration cannot be found."""

    def __init__(
        self: Self,
        registry_name: str,
        key: MigrationKey,
    ) -> None:
        """Initializes MigrationNotFoundError."""
        self.key = key
        msg = f"Migration not found: {key[0]} → {key[1]}"
        super().__init__(registry_name, msg)


class MigrationAlreadyRegisteredError(RegistryError):
    """Raised when a migration is already registered."""

    def __init__(
        self: Self,
        registry_name: str,
        key: MigrationKey,
    ) -> None:
        """Initializes MigrationAlreadyRegisteredError."""
        self.key = key
        msg = f"Migration already registered: {key[0]} → {key[1]}"
        super().__init__(registry_name, msg)


class MigrationPathIntegrityError(RegistryError):
    """Raised when an operation would break a kind's migration path."""

    def __init__(self, registry_name: str, key: MigrationKey) -> None:
        self.key = key
        super().__init__(
            registry_name,
            f"Cannot remove {key[0]}→{key[1]}: "
            "it is on the migration path. Remove with force or register a replacement.",
        )


class MigrationMissingFieldError(VersionedModelError):
    """Raised when the payload is structurally incompatible with the
    container model — a required field is missing."""

    def __init__(
        self: Self,
        registry_name: str,
        version: VersionValue,
        field_name: str,
    ) -> None:
        self.field_name = field_name
        msg = f"Required field '{field_name}' is missing in payload for {registry_name} - {version}"  # noqa: E501
        super().__init__(registry_name, version, msg)


class EngineError(Exception):
    """Raised when the engine encounters an error."""

    def __init__(
        self: Self,
        msg: str,
    ) -> None:
        """Initializes EngineError."""
        self.msg = msg
        super().__init__(msg)


class DiscoveryError(EngineError):
    """Raised when payload discovery fails."""


class DiscoveryValidationError(DiscoveryError):
    """Raised when the payload does not conform to the container schema."""

    def __init__(
        self: Self,
        path: tuple[str | int, ...],
        message: str,
    ) -> None:
        """Initializes DiscoveryValidationError."""
        self.path = path
        super().__init__(f"Discovery validation failed at {path}: {message}")


class MaxDepthExceededError(DiscoveryError):
    """Raised when a versioned entry is found deeper than ``max_migration_depth``."""

    def __init__(
        self: Self,
        path: tuple[str | int, ...],
        depth: int,
        kind: str,
        version: str,
        max_depth: int,
    ) -> None:
        """Initializes MaxDepthExceededError."""
        self.path = path
        self.depth = depth
        self.kind = kind
        self.version = version
        self.max_depth = max_depth
        super().__init__(
            f"Versioned entry {kind}@{version} at path {path} (depth {depth}) "
            f"exceeds max_migration_depth ({max_depth})."
        )


class MigrationError(Exception):
    """Raised when a migration fails or cannot be found."""

    def __init__(
        self: Self,
        kind: Any | Sequence[Any],
        source: Any | None = None,
        target: Any | None = None,
        reason: str | None = None,
    ) -> None:
        """Initializes MigrationError.

        Accepts either the old ``(source, target)`` form or the explicit
        ``kind, source, target`` form for convenience.
        """
        source_kind, target_kind = None, None
        if isinstance(kind, tuple) and len(kind) == _ENDPOINT_PAIR and source is None:
            source, target = kind
            kind = "unknown"
        if source is not None and hasattr(source, "version"):
            source_kind = source.kind
        if target is not None and hasattr(target, "version"):
            target_kind = target.kind
        display_kind = kind or source_kind or target_kind or "unknown"

        self.kind = display_kind
        self.source = source
        self.target = target
        self.reason = reason
        msg = f"Migration failed: {display_kind} {source} → {target}"
        if reason:
            msg += f"\nReason: {reason}"
        super().__init__(msg)
