from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol, runtime_checkable

from pyverge.core.types import HookState
from pyverge.core.versioning import Migratable
from pyverge.runtime.context import StepContext


@runtime_checkable
class HookScope(Protocol):
    """Per-step resource scope returned by a hook."""

    def __enter__(self) -> object: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


@runtime_checkable
class AsyncHookScope(Protocol):
    """Per-step async resource scope returned by a hook."""

    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


@runtime_checkable
class MigrationHook(Protocol):
    """No-op migration hook; subclasses override either seam."""

    def before_migrate(
        self,
        step: StepContext,
        data: dict[str, Any],
        *,
        state: HookState,
    ) -> HookScope | AsyncHookScope | None: ...

    def after_migrate(
        self,
        step: StepContext,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
        *,
        state: HookState,
    ) -> None: ...

    def on_error(
        self,
        step: StepContext,
        data: dict[str, Any],
        error: Exception,
        *,
        state: HookState,
    ) -> None: ...


Attachable = MigrationHook
"""Backward-compatible alias for the migration hook protocol."""

MigrationHookMap = dict[Migratable, list[Attachable]]


__all__ = [
    "AsyncHookScope",
    "Attachable",
    "HookScope",
    "HookState",
    "MigrationHook",
    "MigrationHookMap",
]
