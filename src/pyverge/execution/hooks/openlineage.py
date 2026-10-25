from __future__ import annotations

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

from pyverge.execution.hooks.types import MigrationHook
from pyverge.versioning import Comparable


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
        self._run_id: str | None = None

    def before_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: dict[str, Any],
    ) -> None:
        self._run_id = uuid4().hex
        kind = getattr(from_version, "kind", "migration")
        self._client.emit(
            RunEvent(
                eventTime=datetime.now(UTC).isoformat(),
                producer=self._producer,
                eventType=RunState.START,
                run=Run(runId=self._run_id),
                job=Job(namespace=self._namespace, name=f"migration.{kind}"),
                inputs=[InputDataset(self._namespace, str(from_version))],
                outputs=[OutputDataset(self._namespace, str(to_version))],
            )
        )

    def after_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
    ) -> None:
        if self._run_id is None:
            return
        kind = getattr(from_version, "kind", "migration")
        self._client.emit(
            RunEvent(
                eventTime=datetime.now(UTC).isoformat(),
                producer=self._producer,
                eventType=RunState.COMPLETE,
                run=Run(runId=self._run_id),
                job=Job(namespace=self._namespace, name=f"migration.{kind}"),
            )
        )
        self._run_id = None

    def on_error(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: dict[str, Any],
        error: Exception,
    ) -> None:
        if self._run_id is None:
            return
        kind = getattr(from_version, "kind", "migration")
        self._client.emit(
            RunEvent(
                eventTime=datetime.now(UTC).isoformat(),
                producer=self._producer,
                eventType=RunState.FAIL,
                run=Run(runId=self._run_id),
                job=Job(namespace=self._namespace, name=f"migration.{kind}"),
            )
        )
        self._run_id = None


__all__ = ["OpenLineageHook"]
