"""Prepared migration: plan + executor + backend, run on demand."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Generic, cast

from pyverge.core.context import MigrationContext
from pyverge.core.exceptions import AsyncExecutionRequired, SyncExecutionRequired
from pyverge.core.types import (
    DirectionViolationStrategy,
    MigrationDirectionStrategy,
    ModelData,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.migration.graph import MigrationPlan
from pyverge.migration.registry import Registry
from pyverge.providers.types import ModelAdapter

from .local.backend import LocalExecutionBackend
from .ports import (
    AsyncExecutionStrategy,
    ExecutionBackend,
    SyncExecutionStrategy,
)
from .types import AsyncExecutor, AsyncMigrationEntry, Executor, MigrationEntry


class MigrationRun(Generic[VersionValue]):
    """A built migration plan bound to an executor and backend.

    Construction does not execute the migration. ``run``/``arun`` accept the
    context at execution time, so the same prepared run can be executed with
    different runtime bindings.
    """

    def __init__(
        self,
        plan: MigrationPlan[VersionValue],
        *,
        executor: Executor[VersionValue] | AsyncExecutor[VersionValue],
        registry: Registry[VersionValue],
        entry_migration: MigrationEntry[VersionValue]
        | AsyncMigrationEntry[VersionValue],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        backend: ExecutionBackend[VersionValue] | None = None,
    ) -> None:
        self.plan = plan
        self.executor = executor
        self._backend: ExecutionBackend[VersionValue] = backend or (
            LocalExecutionBackend(
                registry=registry,
                entry_migration=entry_migration,
                adapter=adapter,
                version_property=version_property,
                direction=direction,
                on_direction_violation=on_direction_violation,
                on_missing_path=on_missing_path,
            )
        )

    @property
    def is_async(self) -> bool:
        """Whether this run is bound to an async executor."""
        return isinstance(self.executor, AsyncExecutor)

    def run(
        self,
        *,
        context: Mapping[str, Any] | MigrationContext | None = None,
    ) -> ModelData:
        """Execute synchronously."""
        if self.is_async:
            raise AsyncExecutionRequired(
                "This migration was prepared for async execution; use arun()"
            )
        return cast("SyncExecutionStrategy[VersionValue]", self.executor).execute(
            self.plan,
            self._backend,
            context=_as_context(context),
        )

    async def arun(
        self,
        *,
        context: Mapping[str, Any] | MigrationContext | None = None,
    ) -> ModelData:
        """Execute asynchronously."""
        if not self.is_async:
            raise SyncExecutionRequired(
                "This migration was prepared for sync execution; use run()"
            )
        return await cast(
            "AsyncExecutionStrategy[VersionValue]", self.executor
        ).aexecute(
            self.plan,
            self._backend,
            context=_as_context(context),
        )


def _as_context(
    value: Mapping[str, Any] | MigrationContext | None,
) -> MigrationContext:
    if isinstance(value, MigrationContext):
        return value
    return MigrationContext.create(value)
