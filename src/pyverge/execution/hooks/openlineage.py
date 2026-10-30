from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from openlineage.client.event_v2 import (
    InputDataset,
    Job,
    OutputDataset,
    Run,
    RunEvent,
    RunState,
)

from pyverge.core.types import HookState
from pyverge.execution.hooks.state import pop_state, push_state
from pyverge.execution.hooks.types import MigrationHook
from pyverge.versioning import MigrationDescriptor, NodeId


@dataclass(frozen=True, slots=True)
class _RunState:
    run_id: str
    job_name: str


class OpenLineageHook(MigrationHook):
    """Emit OpenLineage edge events for one migration edge."""

    def __init__(
        self,
        *,
        client: Any,
        namespace: str,
        producer: str,
    ) -> None:
        self._client = client
        self._namespace = namespace
        self._producer = producer

    def before_migrate(  # noqa: PLR0913
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        data: dict[str, Any],
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None:
        job_name = self._job_name(from_version, to_version)
        run_state = _RunState(run_id=uuid4().hex, job_name=job_name)
        push_state(state, id(self), run_state)
        self._client.emit(
            RunEvent(
                eventTime=datetime.now(UTC).isoformat(),
                producer=self._producer,
                eventType=RunState.START,
                run=Run(runId=run_state.run_id),
                job=Job(namespace=self._namespace, name=run_state.job_name),
                inputs=[InputDataset(self._namespace, str(from_version))],
                outputs=[OutputDataset(self._namespace, str(to_version))],
            )
        )

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
    ) -> None:
        run_state = pop_state(state, id(self))
        if not isinstance(run_state, _RunState):
            return
        self._client.emit(
            RunEvent(
                eventTime=datetime.now(UTC).isoformat(),
                producer=self._producer,
                eventType=RunState.COMPLETE,
                run=Run(runId=run_state.run_id),
                job=Job(namespace=self._namespace, name=run_state.job_name),
            )
        )

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
    ) -> None:
        run_state = pop_state(state, id(self))
        if not isinstance(run_state, _RunState):
            return
        self._client.emit(
            RunEvent(
                eventTime=datetime.now(UTC).isoformat(),
                producer=self._producer,
                eventType=RunState.FAIL,
                run=Run(runId=run_state.run_id),
                job=Job(namespace=self._namespace, name=run_state.job_name),
            )
        )

    @staticmethod
    def _job_name(from_version: NodeId, to_version: NodeId) -> str:
        return (
            f"migration.{from_version.kind}."
            f"{from_version.version}->{to_version.version}"
        )


__all__ = ["OpenLineageHook"]
