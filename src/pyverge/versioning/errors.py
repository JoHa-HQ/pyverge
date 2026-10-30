from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Self

from pyverge.core.errors import CatalogError, PyvergeError
from pyverge.core.types import MIGRATION_PAIR_LEN

if TYPE_CHECKING:
    from pyverge.versioning.types import MigrationKey


class MigrationApplicationError(PyvergeError):
    """Raised when a migration callable fails or cannot be applied."""

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
        msg = f"Migration failed for {display_kind}"
        if source is not None and target is not None:
            msg = f"Migration failed: {source} → {target}"
        if reason:
            msg = f"{msg}: {reason}"
        super().__init__(msg)


class NodeConflictError(PyvergeError):
    """Raised when two full nodes share identity but not field surface."""

    def __init__(self: Self, existing: Any, incoming: Any) -> None:
        self.existing = existing
        self.incoming = incoming
        super().__init__(
            f"Node {incoming} conflicts with {existing}: field surfaces differ"
        )


__all__ = [
    "BackwardCompatibilityError",
    "MigrationApplicationError",
    "NodeConflictError",
]


class BackwardCompatibilityError(CatalogError):
    """Raised when a declared backward-compatible migration is structural breaking."""

    def __init__(
        self: Self,
        catalog_name: str,
        key: MigrationKey,
        *,
        removed: tuple[str, ...],
        modified: tuple[str, ...],
        required_additions: tuple[str, ...],
    ) -> None:
        self.key = key
        self.removed = removed
        self.modified = modified
        self.required_additions = required_additions
        details = []
        if removed:
            details.append(f"removed={list(removed)}")
        if modified:
            details.append(f"modified={list(modified)}")
        if required_additions:
            details.append(f"required_additions={list(required_additions)}")
        super().__init__(
            catalog_name,
            f"Migration {key[0]} → {key[1]} was declared backward-compatible "
            f"but is structurally breaking ({', '.join(details)})",
        )
