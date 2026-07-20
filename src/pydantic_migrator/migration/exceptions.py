"""Exceptions."""

from typing import Self
from .types import MigrationKey, ModelVersionKey, VModel, VersionValue


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
        key: ModelVersionKey | type[VModel],
    ) -> None:
        """Initializes ModelNotFoundError."""
        self.key = key
        super().__init__(
            registry_name,
            f"Model not found: {key}"
        )


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
        from_version: ModelVersionKey,
        to_version: ModelVersionKey,
    ) -> None:
        """Initializes MigrationPathNotFoundError."""
        self.from_version = from_version
        self.to_version = to_version
        msg = f"Migration path not found: {from_version} → {to_version}"
        super().__init__(registry_name, msg)


class MigrationError(RegistryError):
    """Raised when a migration fails or cannot be found."""

    def __init__(
        self: Self,
        registry_name: str,
        key: MigrationKey,
        reason: str | None = None,
    ) -> None:
        """Initializes MigrationError."""
        self.key = key
        self.reason = reason
        msg = f"Migration failed: {key[0]} → {key[1]}"
        if reason:
            msg += f"\nReason: {reason}"
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
