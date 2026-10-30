from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pyverge.core.types import HookState
from pyverge.versioning import MigrationDescriptor, NodeId


@runtime_checkable
class MigrationHook(Protocol):
    """No-op migration hook; subclasses override either seam."""

    def before_migrate(  # noqa: PLR0913
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        data: dict[str, Any],
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None: ...

    def after_migrate(  # noqa: PLR0913
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None: ...

    def on_error(  # noqa: PLR0913
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        data: dict[str, Any],
        error: Exception,
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None: ...


__all__ = ["HookState", "MigrationHook"]
