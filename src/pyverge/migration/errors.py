"""Convergence errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from pyverge.registry.errors import CatalogError

if TYPE_CHECKING:
    from pyverge.versioning import MigrationKey


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


__all__ = ["BackwardCompatibilityError"]
