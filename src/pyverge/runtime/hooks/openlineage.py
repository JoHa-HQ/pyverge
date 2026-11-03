from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
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
from pyverge.runtime.context import StepContext
from pyverge.runtime.hooks.types import HookScope, MigrationHook


@dataclass
class _LineageScope:
    """One OpenLineage run event pair for one migration step."""

    client: Any
    namespace: str
    producer: str
    step: StepContext
    run_id: str = field(default_factory=lambda: uuid4().hex)
    job_name: str = field(init=False)

    def __post_init__(self) -> None:
        self.job_name = self._job_name(self.step)

    def __enter__(self) -> _LineageScope:
        self.client.emit(self._event(RunState.START))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        event_type = RunState.FAIL if exc is not None else RunState.COMPLETE
        self.client.emit(self._event(event_type))

    def _event(self, event_type: RunState) -> RunEvent:
        return RunEvent(
            eventTime=datetime.now(UTC).isoformat(),
            producer=self.producer,
            eventType=event_type,
            run=Run(runId=self.run_id),
            job=Job(namespace=self.namespace, name=self.job_name),
            inputs=[InputDataset(self.namespace, str(self.step.source))],
            outputs=[OutputDataset(self.namespace, str(self.step.target))],
        )

    @staticmethod
    def _job_name(step: StepContext) -> str:
        base = (
            f"migration.{step.source.kind}.{step.source.version}->{step.target.version}"
        )
        if step.edge.is_default_discriminator:
            return base
        return f"{base}.{step.edge.discriminator}"


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

    def before_migrate(
        self,
        step: StepContext,
        data: dict[str, Any],
        *,
        state: HookState,
    ) -> HookScope:
        return _LineageScope(
            client=self._client,
            namespace=self._namespace,
            producer=self._producer,
            step=step,
        )

    def after_migrate(
        self,
        step: StepContext,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
        *,
        state: HookState,
    ) -> None:
        return None

    def on_error(
        self,
        step: StepContext,
        data: dict[str, Any],
        error: Exception,
        *,
        state: HookState,
    ) -> None:
        return None


__all__ = ["OpenLineageHook"]
