from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic

from pyverge.core.exceptions import MigrationError
from pyverge.core.types import (
    DirectionViolationStrategy,
    MigrationDirectionStrategy,
    ModelData,
    VersionMissingStrategy,
    VersionValue,
)

from .graph import GraphEntry

if TYPE_CHECKING:
    from pyverge.types import ModelAdapter


class _DefaultMigrationTask:
    """Runnable migration produced by :class:`DefaultMigrationEntry`."""

    def __init__(
        self,
        entry: GraphEntry[Any, ModelBase],
        current: ModelData,
        *,
        execute_step: Callable[
            [
                Any,
                Any,
                ModelData,
                tuple[Any, ...],
                str,
            ],
            ModelData,
        ],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
    ) -> None:
        self._entry = entry
        self._current = current
        self._execute_step = execute_step
        self._adapter = adapter
        self._version_property = version_property
        self._direction = direction
        self._on_direction_violation = on_direction_violation
        self._on_missing_path = on_missing_path

    def run(self) -> ModelData:
        entry = self._entry
        current = self._current

        if entry.source == entry.target:
            return current

        if not _direction_allowed(entry.source, entry.target, self._direction):
            if self._on_direction_violation == "raise":
                raise MigrationError(
                    entry.kind,
                    entry.source,
                    entry.target,
                    f"Direction {self._direction} blocked for {entry.kind}",
                )
            return current

        data = current
        try:
            for (step_from, step_to), hooks in zip(entry.steps, entry.hooks):
                data = self._execute_step(
                    step_from, step_to, data, hooks, self._version_property
                )
        except MigrationError:
            if self._on_missing_path == "raise":
                raise
            return current

        if entry.target_model is not None:
            data = self._adapter.finalize(entry.target_model, data)

        return data


class DefaultMigrationEntry(Generic[VersionValue]):
    """Default per-entry migration: direction check, step execution, finalize."""

    def migrate(
        self,
        entry: GraphEntry[VersionValue, ModelBase],
        current: ModelData,
        *,
        execute_step: Callable[
            [
                Any,
                Any,
                ModelData,
                tuple[Any, ...],
                str,
            ],
            ModelData,
        ],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
    ) -> RunnableMigration:
        return _DefaultMigrationTask(
            entry,
            current,
            execute_step=execute_step,
            adapter=adapter,
            version_property=version_property,
            direction=direction,
            on_direction_violation=on_direction_violation,
            on_missing_path=on_missing_path,
        )


def _direction_allowed(
    source: Any,
    target: Any,
    direction: MigrationDirectionStrategy,
) -> bool:
    if direction == "any" or source == target:
        return True
    if direction == "forward":
        return source < target
    if direction == "backward":
        return source > target
    return True
