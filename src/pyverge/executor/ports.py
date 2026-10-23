"""Execution ports: strategy, backend, and step invocation seams."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pyverge.core.context import MigrationContext
from pyverge.core.types import (
    Attachable,
    ModelData,
    Versionable,
    VersionValue,
    VersionValue_co,
)

if TYPE_CHECKING:
    from pyverge.migration.graph import GraphEntry, MigrationPlan


class StepInvoker(Protocol[VersionValue_co]):
    """Port for invoking one resolved migration step."""

    def execute_step(
        self,
        step_from: Versionable,
        step_to: Versionable,
        data: ModelData,
        hooks: tuple[Attachable, ...],
        vp: str,
        context: MigrationContext | None = None,
    ) -> ModelData: ...

    async def aexecute_step(
        self,
        step_from: Versionable,
        step_to: Versionable,
        data: ModelData,
        hooks: tuple[Attachable, ...],
        vp: str,
        context: MigrationContext | None = None,
    ) -> ModelData: ...


class ExecutionBackend(Protocol[VersionValue]):
    """Runs entries and steps for a prepared plan.

    Local and remote backends implement this port. Strategies never touch the
    registry, adapter, or migration catalog directly.
    """

    def ensure_compatible(self, plan: MigrationPlan[VersionValue]) -> None: ...

    def run_entry(
        self,
        entry: GraphEntry[VersionValue],
        current: ModelData,
        context: MigrationContext | None = None,
    ) -> ModelData: ...

    async def arun_entry(
        self,
        entry: GraphEntry[VersionValue],
        current: ModelData,
        context: MigrationContext | None = None,
    ) -> ModelData: ...


class SyncExecutionStrategy(Protocol[VersionValue]):
    """A sync plan executor selected by :class:`ExecutionPolicy`."""

    def execute(
        self,
        plan: MigrationPlan[VersionValue],
        backend: ExecutionBackend[VersionValue],
        *,
        context: MigrationContext | None = None,
    ) -> ModelData: ...


class AsyncExecutionStrategy(Protocol[VersionValue]):
    """An async plan executor selected by :class:`ExecutionPolicy`."""

    async def aexecute(
        self,
        plan: MigrationPlan[VersionValue],
        backend: ExecutionBackend[VersionValue],
        *,
        context: MigrationContext | None = None,
    ) -> ModelData: ...
