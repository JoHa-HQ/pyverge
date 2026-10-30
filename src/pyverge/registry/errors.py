from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Self

from pyverge.core.errors import CatalogError, PyvergeError
from pyverge.core.types import MIGRATION_PAIR_LEN, ModelHandle

if TYPE_CHECKING:
    from pyverge.versioning import MigrationKey, ModelRef


class GraphLockedError(CatalogError):
    """Raised when a build operation targets a locked catalog."""

    def __init__(self: Self, catalog_name: str, operation: str) -> None:
        self.operation = operation
        super().__init__(
            catalog_name,
            f"Catalog {catalog_name!r} is locked; cannot {operation}",
        )


class ModelNotFoundError(CatalogError):
    """Raised when a model or version cannot be found in the catalog."""

    def __init__(
        self: Self,
        catalog_name: str,
        key: Any | ModelHandle | ModelRef,
    ) -> None:
        self.key = key
        super().__init__(catalog_name, f"Model not found: {key}")


class ModelAlreadyRegisteredError(CatalogError):
    """Raised when a model is already registered."""

    def __init__(self: Self, catalog_name: str, version: Any) -> None:
        self.version = version
        super().__init__(
            catalog_name, f"Model at version '{version}' is already registered"
        )


class ModelConflictError(ModelAlreadyRegisteredError):
    """Raised when a re-registration declares a different field surface."""

    def __init__(
        self: Self,
        catalog_name: str,
        version: Any,
        registered: frozenset[str],
        incoming: frozenset[str],
        *,
        subject: str | None = None,
    ) -> None:
        super().__init__(catalog_name, version)
        self.registered = registered
        self.incoming = incoming
        self.missing = registered - incoming
        self.extra = incoming - registered
        self.subject = subject or str(version)
        PyvergeError.__init__(
            self,
            f"{self.subject} is already registered with fields "
            f"{sorted(registered)}, but the new registration declares "
            f"{sorted(incoming)} "
            f"(missing: {sorted(self.missing)}, extra: {sorted(self.extra)}). "
            "Resolve by aligning this declaration to the registered surface, "
            "aligning the registered model to it, or giving the change its own "
            "version.",
        )


class MissingReferenceError(CatalogError):
    """Raised when a registered model references an unregistered version."""

    def __init__(
        self: Self,
        catalog_name: str,
        version: Any,
        absent: frozenset[Any],
        *,
        subject: str | None = None,
    ) -> None:
        self.version = version
        self.absent = absent
        self.subject = subject or str(version)
        rendered = ", ".join(str(item) for item in sorted(absent))
        super().__init__(
            catalog_name,
            f"{self.subject} references versioned kinds that are not "
            f"registered ({rendered}); there is no implicit registration. "
            "Register a model for every referenced version, or give the "
            "reference its own manager.",
        )


class MigrationNotFoundError(CatalogError):
    """Raised when a migration cannot be found."""

    def __init__(self: Self, catalog_name: str, key: MigrationKey) -> None:
        self.key = key
        super().__init__(catalog_name, f"Migration not found: {key[0]} → {key[1]}")


class MigrationAlreadyRegisteredError(CatalogError):
    """Raised when a migration is already registered."""

    def __init__(self: Self, catalog_name: str, key: MigrationKey) -> None:
        self.key = key
        super().__init__(
            catalog_name, f"Migration already registered: {key[0]} → {key[1]}"
        )


class MigrationConflictError(MigrationAlreadyRegisteredError):
    """Raised when the same endpoint pair is re-registered with new content."""

    def __init__(
        self: Self,
        catalog_name: str,
        key: MigrationKey,
        *,
        registered_hash: str,
        incoming_hash: str,
    ) -> None:
        self.registered_hash = registered_hash
        self.incoming_hash = incoming_hash
        super().__init__(catalog_name, key)
        self.args = (
            f"Migration conflict for {key[0]} → {key[1]}: "
            f"content {registered_hash[:12]} != {incoming_hash[:12]}",
        )


class MigrationPathIntegrityError(CatalogError):
    """Raised when an operation would break a kind's migration path."""

    def __init__(self: Self, catalog_name: str, key: MigrationKey) -> None:
        self.key = key
        super().__init__(
            catalog_name,
            f"Cannot remove {key[0]}→{key[1]}: "
            "it is on the migration path. Remove with force or register a replacement.",
        )


class MigrationPathError(PyvergeError):
    """Raised when a migration path cannot be resolved."""

    def __init__(
        self: Self,
        kind: Any | Sequence[Any],
        source: Any | None = None,
        target: Any | None = None,
        reason: str | None = None,
    ) -> None:
        source_kind, target_kind = None, None
        if (
            isinstance(kind, tuple)
            and len(kind) == MIGRATION_PAIR_LEN
            and source is None
        ):
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
        msg = f"Cannot resolve migration path for {display_kind}"
        if source is not None and target is not None:
            msg = f"Cannot resolve migration path: {source} → {target}"
        if reason:
            msg = f"{msg}: {reason}"
        super().__init__(msg)


__all__ = [
    "CatalogError",
    "GraphLockedError",
    "MigrationAlreadyRegisteredError",
    "MigrationConflictError",
    "MigrationNotFoundError",
    "MigrationPathError",
    "MigrationPathIntegrityError",
    "MissingReferenceError",
    "ModelAlreadyRegisteredError",
    "ModelConflictError",
    "ModelNotFoundError",
]
