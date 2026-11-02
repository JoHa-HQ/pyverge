"""Shared convergence runtime for framework adapters."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pyverge.core import MigrationContext
from pyverge.core.types import ModelData
from pyverge.manager import Manager
from pyverge.manager.types import TargetPolicy
from pyverge.registry import HealthFailLevel

if TYPE_CHECKING:
    from pyverge.execution import Runner


class ConvergenceRuntime:
    """One runner and one convergence path shared by framework bindings.

    Adapters bind the runner during application startup, translate
    :class:`HealthValidationError` into their native error, and inject a
    context factory when the framework exposes request/message context.
    """

    def __init__(  # noqa: PLR0913
        self,
        manager: Manager,
        runner: Runner | None = None,
        *,
        context: MigrationContext | None = None,
        run_id: str | None = None,
        context_factory: Callable[[Any], MigrationContext | None] | None = None,
        validate_target: bool = False,
        health_fail_level: HealthFailLevel = "error",
    ) -> None:
        self._manager = manager
        self._runner = runner
        self._context = context
        self._run_id = run_id
        self._context_factory = context_factory
        self._validate_target = validate_target
        self._health_fail_level = health_fail_level

    @property
    def manager(self) -> Manager:
        """Return the graph manager."""
        return self._manager

    @property
    def runner(self) -> Runner:
        """Return the bound runner.

        Raises:
            RuntimeError: If the application has not bound a runner yet.
        """
        if self._runner is None:
            raise RuntimeError(
                "ConvergenceRuntime has no runner; bind one during application startup"
            )
        return self._runner

    def bind(self, runner: Runner) -> None:
        """Bind the runner created by the application lifespan.

        Args:
            runner: Fully configured runner for this application.

        Raises:
            RuntimeError: If a different runner is already bound.
        """
        if self._runner is not None and self._runner is not runner:
            raise RuntimeError("ConvergenceRuntime is already bound to a runner")
        self._runner = runner

    def validate_health(self) -> None:
        """Validate the registry at the configured fail level.

        Forwards to ``Manager.health`` and may raise
        :class:`HealthValidationError` when an issue meets the fail level.
        """
        self._manager.health(fail_level=self._health_fail_level)

    def context_for(self, source: Any = None) -> MigrationContext | None:
        """Return the migration context for one request or message."""
        if self._context_factory is not None and source is not None:
            return self._context_factory(source)
        return self._context

    def dump(self, value: object) -> ModelData:
        """Dump a handler return value into a payload mapping."""
        return self._manager.dump(value)

    def _run(  # noqa: PLR0913
        self,
        payload: ModelData,
        target: TargetPolicy,
        *,
        source_model: type[Any] | None,
        max_depth: int,
        context: MigrationContext | None,
        run_id: str | None,
        validate_target: bool | None,
    ) -> Any:
        return self.runner.run(
            payload,
            target,
            source_model=source_model,
            max_depth=max_depth,
            context=self._context if context is None else context,
            run_id=self._run_id if run_id is None else run_id,
            validate_target=(
                self._validate_target if validate_target is None else validate_target
            ),
        )

    def converge_sync(  # noqa: PLR0913
        self,
        payload: ModelData,
        target: TargetPolicy,
        *,
        source_model: type[Any] | None = None,
        max_depth: int = -1,
        context: MigrationContext | None = None,
        run_id: str | None = None,
        validate_target: bool | None = None,
    ) -> ModelData:
        """Converge on a synchronous runner.

        Args:
            payload: Source payload before migration.
            target: Target policy resolved by the graph.
            source_model: Source model used to validate and guide traversal.
            max_depth: Maximum source nesting depth; ``-1`` is unbounded.
            context: Migration context for hooks and middleware.
            run_id: Run identifier for telemetry.
            validate_target: Override the runtime's target-validation default.

        Returns:
            ModelData: The converged payload.

        Raises:
            RuntimeError: If the bound runner is asynchronous.
        """
        migrated = self._run(
            payload,
            target,
            source_model=source_model,
            max_depth=max_depth,
            context=context,
            run_id=run_id,
            validate_target=validate_target,
        )
        if inspect.isawaitable(migrated):
            if inspect.iscoroutine(migrated):
                migrated.close()
            raise RuntimeError("sync convergence requires a synchronous runner")
        return migrated

    async def converge(  # noqa: PLR0913
        self,
        payload: ModelData,
        target: TargetPolicy,
        *,
        source_model: type[Any] | None = None,
        max_depth: int = -1,
        context: MigrationContext | None = None,
        run_id: str | None = None,
        validate_target: bool | None = None,
    ) -> ModelData:
        """Converge a source payload to *target*.

        Args:
            payload: Source payload before migration.
            target: Target policy resolved by the graph.
            source_model: Source model used to validate and guide traversal.
            max_depth: Maximum source nesting depth; ``-1`` is unbounded.
            context: Migration context for hooks and middleware.
            run_id: Run identifier for telemetry.
            validate_target: Override the runtime's target-validation default.

        Returns:
            ModelData: The converged payload.
        """
        migrated = self._run(
            payload,
            target,
            source_model=source_model,
            max_depth=max_depth,
            context=context,
            run_id=run_id,
            validate_target=validate_target,
        )
        if inspect.isawaitable(migrated):
            migrated = await migrated
        return migrated


__all__ = ["ConvergenceRuntime"]
