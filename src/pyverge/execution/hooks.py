"""Execution hook defaults."""

from __future__ import annotations

from typing import Any

from pyverge.versioning import Comparable


class MigrationHook:
    """No-op migration hook; subclasses override either seam."""

    def before_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: dict[str, Any],
    ) -> None:
        """Called before an edge runs."""
        return None

    def after_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
    ) -> None:
        """Called after an edge runs."""
        return None

    def on_error(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: dict[str, Any],
        error: Exception,
    ) -> None:
        """Called when an edge fails."""
        return None


__all__ = ["MigrationHook"]
