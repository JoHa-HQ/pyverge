from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
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
from pyverge.core.types import HookState
from pyverge.runtime.context import DatasetContext, StepContext
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
        self.client.emit(self._event(event_type, error=exc))

    def _event(
        self, event_type: RunState, *, error: BaseException | None = None
    ) -> RunEvent:
        return RunEvent(
            eventTime=datetime.now(UTC).isoformat(),
            producer=self.producer,
            eventType=event_type,
            run=Run(runId=self.run_id, facets=self._run_facets(error)),
            job=Job(
                namespace=self.namespace,
                name=self.job_name,
                facets=self._job_facets(),
            ),
            inputs=[
                InputDataset(
                    self.namespace,
                    self.step.source_dataset.name,
                    facets=self._dataset_facets(self.step.source_dataset),
                )
            ],
            outputs=[
                OutputDataset(
                    self.namespace,
                    self.step.target_dataset.name,
                    facets=self._dataset_facets(self.step.target_dataset),
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

    def _job_facets(self) -> dict[str, Any]:
        tags = [
            tags_job.TagsJobFacetFields(
                key="pyverge.migration.name",
                value=self.step.name,
            ),
            tags_job.TagsJobFacetFields(
                key="pyverge.migration.discriminator",
                value=self.step.edge.discriminator,
            ),
        ]
        if self.step.migration is not None:
            tags.extend(
                [
                    tags_job.TagsJobFacetFields(
                        key="pyverge.migration.strategy",
                        value=self.step.migration.strategy,
                    ),
                    tags_job.TagsJobFacetFields(
                        key="pyverge.migration.identity",
                        value=self.step.migration.identity,
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

    def _run_facets(self, error: BaseException | None) -> dict[str, Any]:
        facets: dict[str, Any] = {
            "processing_engine": processing_engine_run.ProcessingEngineRunFacet(
                name="pyverge",
                version=__version__,
            ),
            "parent": parent_run.ParentRunFacet(
                run=parent_run.Run(
                    runId=str(uuid5(NAMESPACE_URL, self.step.run.run_id))
                ),
                job=parent_run.Job(
                    namespace=self.namespace,
                    name="migration.run",
                ),
            ),
        }
        if error is not None:
            facets["error"] = error_message_run.ErrorMessageRunFacet(
                message=str(error),
                programmingLanguage="python",
            )
        return facets

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
