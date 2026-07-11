"""Exceptions."""

from typing import Self, cast

from pendulum import Date
from pydantic import BaseModel
from semver import Version

from .types import VersionValue


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
        version: VersionValue,
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
        lookup_key: VersionValue | type[BaseModel],
    ) -> None:
        """Initializes ModelNotFoundError."""
        self.lookup_key = lookup_key
        if isinstance(lookup_key, Version) or isinstance(lookup_key, Date):
            msg = f"Model version '{lookup_key}' not found in '{registry_name}'"
        elif issubclass(lookup_key, BaseModel):
            msg = f"Model version '{lookup_key.__name__}' not found in '{registry_name}'"
        super().__init__(registry_name, msg)


class ModelAlreadyRegisteredError(RegistryError):
    """Raised when a model is already registered."""

    def __init__(
        self: Self,
        registry_name: str,
        version: VersionValue,
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
        from_version: VersionValue,
        to_version: VersionValue,
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
        from_version: object,
        to_version: object,
        reason: str | None = None,
    ) -> None:
        """Initializes MigrationError."""
        self.from_version = from_version
        self.to_version = to_version
        self.reason = reason
        msg = f"Migration failed: {from_version} → {to_version}"
        if reason:
            msg += f"\nReason: {reason}"
        super().__init__(registry_name, msg)


class MigrationNotFoundError(RegistryError):
    """Raised when a migration cannot be found."""

    def __init__(
        self: Self,
        registry_name: str,
        from_version: object,
        to_version: object,
    ) -> None:
        """Initializes MigrationNotFoundError."""
        self.from_version = from_version
        self.to_version = to_version
        msg = f"Migration not found: {from_version} → {to_version}"
        super().__init__(registry_name, msg)


class MigrationAlreadyRegisteredError(RegistryError):
    """Raised when a migration is already registered."""

    def __init__(
        self: Self,
        registry_name: str,
        from_version: object,
        to_version: object,
    ) -> None:
        """Initializes MigrationAlreadyRegisteredError."""
        self.from_version = from_version
        self.to_version = to_version
        msg = f"Migration already registered: {from_version} → {to_version}"
        super().__init__(registry_name, msg)


class InvalidVersionError(RegistryError):
    """Raised when a version string cannot be parsed."""

    def __init__(
        self: Self,
        registry_name: str,
        version: VersionValue_co,
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
        msg = f"Required field '{field_name}' is missing in payload for {registry_name} - {version}"
        super().__init__(registry_name, version, msg)
