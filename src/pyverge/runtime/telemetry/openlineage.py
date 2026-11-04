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


@dataclass(frozen=True, slots=True)
class _LineageEvents:
    """Project runtime lifecycle events into OpenLineage events and facets."""

    producer: str

    def run_started(self, event: RunStarted) -> RunEvent:
        return RunEvent(
            eventTime=self._now(),
            producer=self.producer,
            eventType=RunState.START,
            run=self._run(event.run.run_id, self._run_facets()),
            job=self._run_job(event.run.namespace),
            inputs=[
                self._input_dataset(entry.source) for entry in event.plan.path.entries
            ],
            outputs=[
                self._output_dataset(entry.target) for entry in event.plan.path.entries
            ],
        )

    def run_finished(
        self,
        event: RunCompleted | RunFailed,
        event_type: RunState,
        *,
        error: BaseException | None,
    ) -> RunEvent:
        return RunEvent(
            eventTime=self._now(),
            producer=self.producer,
            eventType=event_type,
            run=self._run(event.run.run_id, self._run_facets(error)),
            job=self._run_job(event.run.namespace),
        )

    def step_started(self, step: StepContext, step_run: _StepRun) -> RunEvent:
        return self._step_event(step, step_run, RunState.START)

    def step_finished(
        self,
        step: StepContext,
        step_run: _StepRun,
        event_type: RunState,
        *,
        error: BaseException | None,
    ) -> RunEvent:
        return self._step_event(step, step_run, event_type, error=error)

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
            producer=self.producer,
            eventType=event_type,
            run=self._run(step_run.run_id, self._step_run_facets(step, error)),
            job=Job(
                namespace=step.run.namespace,
                name=step_run.job_name,
                facets=self._job_facets(step),
            ),
            inputs=[self._dataset_input(step.source_dataset)],
            outputs=[self._dataset_output(step.target_dataset)],
        )

    def _run(self, run_id: str, facets: dict[str, Any]) -> Run:
        return Run(
            runId=str(uuid5(NAMESPACE_URL, run_id)),
            facets=facets,
        )

    def _run_job(self, namespace: str) -> Job:
        return Job(
            namespace=namespace,
            name=_RUN_JOB,
            facets=self._run_job_facets(),
        )

    def _input_dataset(self, node: Any) -> InputDataset:
        return self._dataset_input(DatasetContext.from_node(node))

    def _output_dataset(self, node: Any) -> OutputDataset:
        return self._dataset_output(DatasetContext.from_node(node))

    def _dataset_input(self, dataset: DatasetContext) -> InputDataset:
        return InputDataset(
            dataset.namespace,
            dataset.name,
            facets=self._dataset_facets(dataset),
        )

    def _dataset_output(self, dataset: DatasetContext) -> OutputDataset:
        return OutputDataset(
            dataset.namespace,
            dataset.name,
            facets=self._dataset_facets(dataset),
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

    @staticmethod
    def _run_job_facets() -> dict[str, Any]:
        return {
            "jobType": job_type_job.JobTypeJobFacet(
                processingType="BATCH",
                integration="pyverge",
                jobType="MIGRATION_RUN",
            ),
        }

    @staticmethod
    def _run_facets(error: BaseException | None = None) -> dict[str, Any]:
        facets: dict[str, Any] = {
            "processing_engine": processing_engine_run.ProcessingEngineRunFacet(
                name="pyverge",
                version=__version__,
            ),
        }
        if error is not None:
            facets["error"] = error_message_run.ErrorMessageRunFacet(
                message=str(error),
                programmingLanguage="python",
            )
        return facets

    @staticmethod
    def _step_run_facets(
        step: StepContext,
        error: BaseException | None,
    ) -> dict[str, Any]:
        facets = _LineageEvents._run_facets(error)
        facets["parent"] = parent_run.ParentRunFacet(
            run=parent_run.Run(runId=str(uuid5(NAMESPACE_URL, step.run.run_id))),
            job=parent_run.Job(namespace=step.run.namespace, name=_RUN_JOB),
        )
        return facets

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()


class OpenLineageAdapter:
    """Translate lifecycle events into OpenLineage run and step events."""

    def __init__(
        self,
        *,
        client: Any,
        producer: str,
    ) -> None:
        self._client = client
        self._events = _LineageEvents(producer)
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
        self._client.emit(self._events.run_started(event))
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
        self._client.emit(self._events.run_finished(event, event_type, error=error))

    def _start_step(self, event: StepStarted) -> None:
        step = event.step
        with self._lock:
            if step.run.run_id not in self._runs:
                return
        step_run = _StepRun(
            run_id=uuid4().hex,
            job_name=self._job_name(step),
        )
        self._client.emit(self._events.step_started(step, step_run))
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
            self._events.step_finished(
                event.step,
                step_run,
                event_type,
                error=error,
            )
        )

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
