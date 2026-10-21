"""Local execution backend: registry + adapter behind the backend port."""

from __future__ import annotations

from typing import Generic, cast

from pyverge.core.context import MigrationContext
from pyverge.core.types import (
    DirectionViolationStrategy,
    MigrationDirectionStrategy,
    ModelData,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.migration.graph import GraphEntry, MigrationPlan
from pyverge.migration.registry import Registry
from pyverge.providers.types import ModelAdapter

from ..types import AsyncMigrationEntry, MigrationEntry
from .step import StepExecutor


class LocalExecutionBackend(Generic[VersionValue]):
    """Run entries locally through the registry and model adapter."""

    def __init__(
        self,
        *,
        registry: Registry[VersionValue],
        entry_migration: MigrationEntry[VersionValue]
        | AsyncMigrationEntry[VersionValue],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
    ) -> None:
        self._registry = registry
        self._entry_migration = entry_migration
        self._adapter = adapter
        self._version_property = version_property
        self._direction = direction
        self._on_direction_violation = on_direction_violation
        self._on_missing_path = on_missing_path
        self._step = StepExecutor(registry)

    def ensure_compatible(self, plan: MigrationPlan[VersionValue]) -> None:
        self._adapter.ensure_compatible(plan.container, fields=plan.target_fields)

    def run_entry(
        self,
        entry: GraphEntry[VersionValue],
        current: ModelData,
        context: MigrationContext | None = None,
    ) -> ModelData:
        task = cast("MigrationEntry[VersionValue]", self._entry_migration).migrate(
            entry,
            current,
            execute_step=self._step.execute_step,
            adapter=self._adapter,
            version_property=self._version_property,
            direction=self._direction,
            on_direction_violation=self._on_direction_violation,
            on_missing_path=self._on_missing_path,
            context=context,
        )
        return task.run()

    async def arun_entry(
        self,
        entry: GraphEntry[VersionValue],
        current: ModelData,
        context: MigrationContext | None = None,
    ) -> ModelData:
        task = cast(
            "AsyncMigrationEntry[VersionValue]", self._entry_migration
        ).amigrate(
            entry,
            current,
            aexecute_step=self._step.aexecute_step,
            adapter=self._adapter,
            version_property=self._version_property,
            direction=self._direction,
            on_direction_violation=self._on_direction_violation,
            on_missing_path=self._on_missing_path,
            context=context,
        )
        return await task.arun()
