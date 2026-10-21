"""Entry migration planning and execution task."""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic

from pyverge.core.context import MigrationContext
from pyverge.core.exceptions import MigrationError
from pyverge.core.types import (
    DirectionViolationStrategy,
    MigrationDirectionStrategy,
    ModelData,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.migration.graph import GraphEntry

if TYPE_CHECKING:
    from pyverge.providers.types import ModelAdapter

    from ..types import (
        AsyncMigrationEntryCallback,
        AsyncRunnableMigration,
        MigrationEntryCallback,
        RunnableMigration,
    )


class EntryMigrationTask(Generic[VersionValue]):
    """Executable command for one discovered entry."""

    def __init__(
        self,
        entry: GraphEntry[VersionValue],
        current: ModelData,
        *,
        execute_step: MigrationEntryCallback | None = None,
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
        aexecute_step: AsyncMigrationEntryCallback | None = None,
    ) -> None:
        self._entry = entry
        self._current = current
        self._execute_step = execute_step
        self._aexecute_step = aexecute_step
        self._adapter = adapter
        self._version_property = version_property
        self._direction = direction
        self._on_direction_violation = on_direction_violation
        self._on_missing_path = on_missing_path
        self._context = context

    def _should_skip(self) -> bool:
        entry = self._entry
        if entry.source == entry.target:
            return True
        if entry.allows_direction(self._direction):
            return False
        if self._on_direction_violation == "raise":
            raise MigrationError(
                entry.kind,
                entry.source,
                entry.target,
                f"Direction {self._direction} blocked for {entry.kind}",
            )
        return True

    def _finalize(self, data: ModelData) -> ModelData:
        if self._entry.target_model is not None:
            return self._adapter.finalize(self._entry.target_model, data)
        return data

    def run(self) -> ModelData:
        if self._should_skip():
            return self._current

        assert self._execute_step is not None
        data = self._current
        try:
            for (step_from, step_to), hooks in zip(
                self._entry.steps, self._entry.hooks
            ):
                data = self._execute_step(
                    step_from,
                    step_to,
                    data,
                    hooks,
                    self._version_property,
                    self._context,
                )
        except MigrationError:
            if self._on_missing_path == "raise":
                raise
            return self._current
        return self._finalize(data)

    async def arun(self) -> ModelData:
        if self._should_skip():
            return self._current

        assert self._aexecute_step is not None
        data = self._current
        try:
            for (step_from, step_to), hooks in zip(
                self._entry.steps, self._entry.hooks
            ):
                data = await self._aexecute_step(
                    step_from,
                    step_to,
                    data,
                    hooks,
                    self._version_property,
                    self._context,
                )
        except MigrationError:
            if self._on_missing_path == "raise":
                raise
            return self._current
        return self._finalize(data)


class DefaultEntryPlanner(Generic[VersionValue]):
    """Stateless factory for per-entry migration tasks."""

    def _create_task(
        self,
        entry: GraphEntry[VersionValue],
        current: ModelData,
        *,
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
        execute_step: MigrationEntryCallback | None = None,
        aexecute_step: AsyncMigrationEntryCallback | None = None,
    ) -> EntryMigrationTask[VersionValue]:
        return EntryMigrationTask(
            entry,
            current,
            execute_step=execute_step,
            aexecute_step=aexecute_step,
            adapter=adapter,
            version_property=version_property,
            direction=direction,
            on_direction_violation=on_direction_violation,
            on_missing_path=on_missing_path,
            context=context,
        )

    def migrate(
        self,
        entry: GraphEntry[VersionValue],
        current: ModelData,
        *,
        execute_step: MigrationEntryCallback,
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
    ) -> RunnableMigration:
        return self._create_task(
            entry,
            current,
            execute_step=execute_step,
            adapter=adapter,
            version_property=version_property,
            direction=direction,
            on_direction_violation=on_direction_violation,
            on_missing_path=on_missing_path,
            context=context,
        )

    def amigrate(
        self,
        entry: GraphEntry[VersionValue],
        current: ModelData,
        *,
        aexecute_step: AsyncMigrationEntryCallback,
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
    ) -> AsyncRunnableMigration:
        return self._create_task(
            entry,
            current,
            aexecute_step=aexecute_step,
            adapter=adapter,
            version_property=version_property,
            direction=direction,
            on_direction_violation=on_direction_violation,
            on_missing_path=on_missing_path,
            context=context,
        )


#: Backward-compatible alias; new name states the planning role.
DefaultMigrationEntry = DefaultEntryPlanner
