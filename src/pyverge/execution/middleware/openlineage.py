"""OpenLineage control middleware."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from openlineage.client.event_v2 import (
    InputDataset,
    Job,
    OutputDataset,
    Run,
    RunEvent,
    RunState,
)


class OpenLineageMiddleware:
    """Control middleware: one OpenLineage run per migration execution."""

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

    def wrap(self, inner: Any) -> Any:
        return _OpenLineageRun(
            inner,
            client=self._client,
            namespace=self._namespace,
            producer=self._producer,
        )


class _OpenLineageRun:
    def __init__(
        self,
        inner: Any,
        *,
        client: Any,
        namespace: str,
        producer: str,
    ) -> None:
        self._inner = inner
        self._client = client
        self._namespace = namespace
        self._producer = producer

    def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        inputs = [
            InputDataset(
                self._namespace,
                f"{entry.source.kind}@{entry.source.version[1]}",
            )
            for entry in plan.path.entries
        ]
        outputs = [
            OutputDataset(
                self._namespace,
                f"{entry.target.kind}@{entry.target.version[1]}",
            )
            for entry in plan.path.entries
        ]
        self._client.emit(
            RunEvent(
                eventTime=datetime.now(UTC).isoformat(),
                producer=self._producer,
                eventType=RunState.START,
                run=Run(runId=run.run_id),
                job=Job(namespace=self._namespace, name="migration.run"),
                inputs=inputs,
                outputs=outputs,
            )
        )
        try:
            result = self._inner.execute(plan, payload, run, adapter)
        except Exception:
            self._client.emit(
                RunEvent(
                    eventTime=datetime.now(UTC).isoformat(),
                    producer=self._producer,
                    eventType=RunState.FAIL,
                    run=Run(runId=run.run_id),
                    job=Job(namespace=self._namespace, name="migration.run"),
                )
            )
            raise
        if hasattr(result, "__await__"):
            return self._async_result(result, run.run_id)
        self._client.emit(
            RunEvent(
                eventTime=datetime.now(UTC).isoformat(),
                producer=self._producer,
                eventType=RunState.COMPLETE,
                run=Run(runId=run.run_id),
                job=Job(namespace=self._namespace, name="migration.run"),
            )
        )
        return result

    async def _async_result(self, result: Any, run_id: str) -> Any:
        try:
            value = await result
        except Exception:
            self._client.emit(
                RunEvent(
                    eventTime=datetime.now(UTC).isoformat(),
                    producer=self._producer,
                    eventType=RunState.FAIL,
                    run=Run(runId=run_id),
                    job=Job(namespace=self._namespace, name="migration.run"),
                )
            )
            raise
        self._client.emit(
            RunEvent(
                eventTime=datetime.now(UTC).isoformat(),
                producer=self._producer,
                eventType=RunState.COMPLETE,
                run=Run(runId=run_id),
                job=Job(namespace=self._namespace, name="migration.run"),
            )
        )
        return value


__all__ = ["OpenLineageMiddleware"]
