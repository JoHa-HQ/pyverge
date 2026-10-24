"""Runtime runner: plan and execute payload migrations."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from pyverge.core.context import MigrationContext
from pyverge.core.types import TargetResolver
from pyverge.execution.coordinator import ExecutionCoordinator
from pyverge.execution.path import Path
from pyverge.execution.plan import ExecutionPlan, ExtractedEntry
from pyverge.execution.types import ConcurrencyBackend, RuntimeCapabilities
from pyverge.schemas.types import ModelAdapter


@dataclass(frozen=True, slots=True)
class Runner:
    """Execute a payload through a frozen graph and configured runtime policy."""

    coordinator: ExecutionCoordinator
    adapter: ModelAdapter
    capabilities: RuntimeCapabilities
    concurrency: ConcurrencyBackend

    def extract(
        self,
        payload: dict[str, Any],
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> list[ExtractedEntry]:
        """Extract versioned entries from a payload."""
        return self.coordinator.extract(
            payload,
            container=container,
            max_depth=max_depth,
        )

    def plan(
        self,
        payload: dict[str, Any],
        target_resolver: TargetResolver,
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> ExecutionPlan:
        """Build a runtime plan through the coordinator."""
        return self.coordinator.plan(
            payload,
            target_resolver,
            container=container,
            max_depth=max_depth,
        )

    def execute(
        self,
        plan: ExecutionPlan,
        *,
        context: MigrationContext | None,
    ) -> dict[str, Any]:
        """Apply every planned migration to a copy of the payload."""
        data = copy.deepcopy(plan.payload)
        for level in plan.levels:
            for entry in level:
                current = Path(*entry.path).get(data)
                for index, (source, target) in enumerate(entry.steps):
                    func = entry.migrations[index]
                    hooks = entry.hooks[index]
                    name = getattr(func, "__name__", f"{source}->{target}")
                    for hook in hooks:
                        hook.before_migrate(name, source, target, current)
                    try:
                        migrated = self.concurrency.run(func, current, context)
                    except Exception as error:
                        for hook in hooks:
                            hook.on_error(name, source, target, current, error)
                        raise
                    for hook in hooks:
                        hook.after_migrate(
                            name,
                            source,
                            target,
                            current,
                            migrated,
                        )
                    if isinstance(migrated, dict):
                        migrated[self.adapter.version_property] = str(target.version[1])
                    current = migrated
                Path(*entry.path).set(data, current)
        return data
