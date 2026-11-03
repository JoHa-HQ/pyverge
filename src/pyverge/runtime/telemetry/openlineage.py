from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from openlineage.client.event_v2 import (
    InputDataset,
    Job,
    OutputDataset,
    Run,
    RunEvent,
    RunState,
)
from openlineage.client.facet_v2 import (
    dataset_version_dataset,
    error_message_run,
    job_type_job,
    parent_run,
    processing_engine_run,
    schema_dataset,
    tags_job,
)

from pyverge._version import __version__
from pyverge.runtime.context import DatasetContext, StepContext

from . import (
    RunCompleted,
    RunFailed,
    RunStarted,
    StepCompleted,
    StepFailed,
    StepStarted,
    TelemetryEvent,
)

_RUN_JOB = "migration.run"


@dataclass(frozen=True, slots=True)
class _StepRun:
    run_id: str
    job_name: str


class OpenLineageAdapter:
    """Translate lifecycle events into OpenLineage run and step events."""

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
        self._lock = Lock()
        self._runs: set[str] = set()
        self._steps: dict[tuple[str, tuple[str | int, ...], int], _StepRun] = {}

    def emit(self, event: TelemetryEvent) -> None:
        if isinstance(event, RunStarted):
            self._start_run(event)
        elif isinstance(event, RunCompleted):
            self._finish_run(event, RunState.COMPLETE, error=None)
        elif isinstance(event, RunFailed):
            self._finish_run(event, RunState.FAIL, error=event.error)
        elif isinstance(event, StepStarted):
            self._start_step(event)
        elif isinstance(event, StepCompleted):
            self._finish_step(event, RunState.COMPLETE, error=None)
        elif isinstance(event, StepFailed):
            self._finish_step(event, RunState.FAIL, error=event.error)

    def _start_run(self, event: RunStarted) -> None:
        self._validate_namespace(event.plan)
        self._client.emit(
            RunEvent(
                eventTime=self._now(),
                producer=self._producer,
                eventType=RunState.START,
                run=Run(
                    runId=self._run_id(event.run.run_id),
                    facets=self._run_facets(),
                ),
                job=Job(
                    namespace=self._namespace,
                    name=_RUN_JOB,
                    facets=self._run_job_facets(),
                ),
                inputs=[
                    InputDataset(
                        self._namespace,
                        (dataset := DatasetContext.from_node(entry.source)).name,
                        facets=self._dataset_facets(dataset),
                    )
                    for entry in event.plan.path.entries
                ],
                outputs=[
                    OutputDataset(
                        self._namespace,
                        (dataset := DatasetContext.from_node(entry.target)).name,
                        facets=self._dataset_facets(dataset),
                    )
                    for entry in event.plan.path.entries
                ],
            )
        )
        with self._lock:
            self._runs.add(event.run.run_id)

    def _finish_run(
        self,
        event: RunCompleted | RunFailed,
        event_type: RunState,
        *,
        error: BaseException | None,
    ) -> None:
        with self._lock:
            if event.run.run_id not in self._runs:
                return
            self._runs.remove(event.run.run_id)
        self._client.emit(
            RunEvent(
                eventTime=self._now(),
                producer=self._producer,
                eventType=event_type,
                run=Run(
                    runId=self._run_id(event.run.run_id),
                    facets=self._run_facets(error),
                ),
                job=Job(
                    namespace=self._namespace,
                    name=_RUN_JOB,
                    facets=self._run_job_facets(),
                ),
            )
        )

    def _start_step(self, event: StepStarted) -> None:
        step = event.step
        with self._lock:
            if step.run.run_id not in self._runs:
                return
        step_run = _StepRun(
            run_id=uuid4().hex,
            job_name=self._job_name(step),
        )
        self._client.emit(self._step_event(step, step_run, RunState.START))
        with self._lock:
            self._steps[self._step_key(step)] = step_run

    def _finish_step(
        self,
        event: StepCompleted | StepFailed,
        event_type: RunState,
        *,
        error: BaseException | None,
    ) -> None:
        key = self._step_key(event.step)
        with self._lock:
            step_run = self._steps.pop(key, None)
        if step_run is None:
            return
        self._client.emit(
            self._step_event(event.step, step_run, event_type, error=error)
        )

    def _step_event(
        self,
        step: StepContext,
        step_run: _StepRun,
        event_type: RunState,
        *,
        error: BaseException | None = None,
    ) -> RunEvent:
        return RunEvent(
            eventTime=self._now(),
            producer=self._producer,
            eventType=event_type,
            run=Run(
                runId=step_run.run_id,
                facets=self._step_run_facets(step, error),
            ),
            job=Job(
                namespace=self._namespace,
                name=step_run.job_name,
                facets=self._job_facets(step),
            ),
            inputs=[
                InputDataset(
                    self._namespace,
                    step.source_dataset.name,
                    facets=self._dataset_facets(step.source_dataset),
                )
            ],
            outputs=[
                OutputDataset(
                    self._namespace,
                    step.target_dataset.name,
                    facets=self._dataset_facets(step.target_dataset),
                )
            ],
        )

    def _dataset_facets(self, dataset: DatasetContext) -> dict[str, Any]:
        facets: dict[str, Any] = {
            "version": dataset_version_dataset.DatasetVersionDatasetFacet(
                datasetVersion=dataset.version,
            ),
        }
        if dataset.fields:
            facets["schema"] = schema_dataset.SchemaDatasetFacet(
                fields=[
                    schema_dataset.SchemaDatasetFacetFields(
                        name=field.name,
                        type=field.type,
                        ordinal_position=index,
                    )
                    for index, field in enumerate(dataset.fields)
                ]
            )
        return facets

    def _job_facets(self, step: StepContext) -> dict[str, Any]:
        tags = [
            tags_job.TagsJobFacetFields(
                key="pyverge.migration.name",
                value=step.name,
            ),
            tags_job.TagsJobFacetFields(
                key="pyverge.migration.discriminator",
                value=step.edge.discriminator,
            ),
        ]
        if step.migration is not None:
            tags.extend(
                [
                    tags_job.TagsJobFacetFields(
                        key="pyverge.migration.strategy",
                        value=step.migration.strategy,
                    ),
                    tags_job.TagsJobFacetFields(
                        key="pyverge.migration.identity",
                        value=step.migration.identity,
                    ),
                ]
            )
        return {
            "jobType": job_type_job.JobTypeJobFacet(
                processingType="BATCH",
                integration="pyverge",
                jobType="MIGRATION",
            ),
            "tags": tags_job.TagsJobFacet(tags=tags),
        }

    def _run_job_facets(self) -> dict[str, Any]:
        return {
            "jobType": job_type_job.JobTypeJobFacet(
                processingType="BATCH",
                integration="pyverge",
                jobType="MIGRATION_RUN",
            ),
        }

    def _run_facets(self, error: BaseException | None = None) -> dict[str, Any]:
        facets: dict[str, Any] = {
            "processing_engine": processing_engine_run.ProcessingEngineRunFacet(
                name="pyverge",
                version=__version__,
            ),
        }
        if error is not None:
            facets["error"] = self._error_facet(error)
        return facets

    def _step_run_facets(
        self,
        step: StepContext,
        error: BaseException | None,
    ) -> dict[str, Any]:
        facets = self._run_facets(error)
        facets["parent"] = parent_run.ParentRunFacet(
            run=parent_run.Run(runId=self._run_id(step.run.run_id)),
            job=parent_run.Job(namespace=self._namespace, name=_RUN_JOB),
        )
        return facets

    def _error_facet(
        self, error: BaseException
    ) -> error_message_run.ErrorMessageRunFacet:
        return error_message_run.ErrorMessageRunFacet(
            message=str(error),
            programmingLanguage="python",
        )

    def _validate_namespace(self, plan: Any) -> None:
        namespaces = {
            entry.source.namespace
            for entry in plan.path.entries
            if entry.source.namespace
        }
        namespaces.update(
            entry.target.namespace
            for entry in plan.path.entries
            if entry.target.namespace
        )
        if namespaces and self._namespace not in namespaces:
            raise ValueError(
                f"OpenLineage namespace {self._namespace!r} does not match "
                f"graph namespace(s) {sorted(namespaces)}"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _run_id(run_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, run_id))

    @staticmethod
    def _step_key(step: StepContext) -> tuple[str, tuple[str | int, ...], int]:
        return (step.run.run_id, step.path, step.index)

    @staticmethod
    def _job_name(step: StepContext) -> str:
        base = (
            f"migration.{step.source.kind}.{step.source.version}->{step.target.version}"
        )
        if step.edge.is_default_discriminator:
            return base
        return f"{base}.{step.edge.discriminator}"


__all__ = ["OpenLineageAdapter"]
