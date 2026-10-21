"""Sequential plan execution."""

from __future__ import annotations

import copy
from typing import Generic

from pyverge.core.context import MigrationContext
from pyverge.core.path import get_at as _get_at_path
from pyverge.core.path import set_at as _set_at_path
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

from .step import StepExecutor
from .types import Executor, MigrationEntry


class SequentialExecutor(Executor[VersionValue], Generic[VersionValue]):
    """Execute plan entries one at a time in topological order."""

    def run(
        self,
        plan: MigrationPlan[VersionValue],
        *,
        registry: Registry[VersionValue],
        entry_migration: MigrationEntry[VersionValue],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
    ) -> ModelData:
        adapter.ensure_compatible(plan.container, fields=plan.target_fields)
        graph = plan.graph
        step_executor = StepExecutor(registry)
        result = copy.deepcopy(plan.data)
        for entry in graph.topological_order():
            current = _get_at_path(result, entry.path)
            task = entry_migration.migrate(
                entry,
                current,
                execute_step=step_executor.execute_step,
                adapter=adapter,
                version_property=version_property,
                direction=direction,
                on_direction_violation=on_direction_violation,
                on_missing_path=on_missing_path,
                context=context,
            )
            migrated = task.run()
            _set_at_path(result, entry.path, migrated)
        return result
