"""Execution hook protocols."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pyverge.versioning import Comparable


@runtime_checkable
class MigrationHook(Protocol):
    """No-op migration hook; subclasses override either seam."""

    def before_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: dict[str, Any],
    ) -> None: ...

    def after_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
    ) -> None: ...

    def on_error(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: dict[str, Any],
        error: Exception,
    ) -> None: ...


__all__ = ["MigrationHook"]
