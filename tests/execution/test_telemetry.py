# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Runtime telemetry lifecycle events and adapters."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, cast

import pytest
import semver
from opentelemetry.trace import StatusCode

from pyverge.core.graph import latest_target_resolver
from pyverge.core.registry import Registry
from pyverge.runtime.backends import AsyncBackend, ProcessBackend, ThreadedBackend
from pyverge.runtime.telemetry import (
    RunCompleted,
    RunStarted,
    StepCompleted,
    StepStarted,
    TelemetryEvent,
)
from pyverge.runtime.telemetry_openlineage import OpenLineageAdapter
from pyverge.runtime.telemetry_otel import OtelAdapter
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2

_BACKENDS = [
    pytest.param((ThreadedBackend, {"max_workers": 0}), id="threaded"),
    pytest.param(
        (
            AsyncBackend,
            {"backend": "asyncio", "backend_options": {}, "max_workers": 0},
        ),
        id="async",
    ),
    pytest.param((ProcessBackend, {"max_workers": 1}), id="process"),
]


def _fail(data: dict[str, Any], context: Any = None) -> dict[str, Any]:
    raise RuntimeError("boom")


_MODELS = [
    [
        PydanticModelAdapter,
        [
            semver.Version,
            "test",
            [UserV1, UserV2],
            [((UserV1, UserV2), migrate_v1_to_v2)],
        ],
    ]
]

_FAILING_MODELS = [
    [
        PydanticModelAdapter,
        [
            semver.Version,
            "test",
            [UserV1, UserV2],
            [((UserV1, UserV2), _fail)],
        ],
    ]
]


class RecordingTelemetry:
    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []

    def emit(self, event: TelemetryEvent) -> None:
        self.events.append(event)


class FailingTelemetry:
    def emit(self, event: TelemetryEvent) -> None:
        raise RuntimeError("telemetry down")


class RecordingSpan:
    def __init__(self, name: str, attributes: dict[str, Any]) -> None:
        self.name = name
        self.attributes = dict(attributes)
        self.status: Any = None
        self.exceptions: list[BaseException] = []
        self.ended = False

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: Any, description: str | None = None) -> None:
        self.status = (status, description)

    def record_exception(self, error: BaseException) -> None:
        self.exceptions.append(error)

    def end(self) -> None:
        self.ended = True


class RecordingScope:
    def __init__(self, span: RecordingSpan) -> None:
        self._span = span

    def __enter__(self) -> RecordingSpan:
        return self._span

    def __exit__(self, *exc_info: Any) -> None:
        self._span.ended = True


class RecordingTracer:
    def __init__(self) -> None:
        self.spans: list[RecordingSpan] = []

    def start_as_current_span(
        self,
        name: str,
        *,
        kind: Any = None,
        attributes: dict[str, Any] | None = None,
    ) -> RecordingScope:
        span = RecordingSpan(name, attributes or {})
        self.spans.append(span)
        return RecordingScope(span)


class RecordingLineageClient:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


def _payload() -> dict[str, Any]:
    return {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@b.c",
            "role": "user",
        }
    }


def _run(runner, registry: Registry) -> dict[str, Any]:
    result = runner.run(
        _payload(),
        latest_target_resolver(registry),
        source_model=None,
        max_depth=-1,
        context=None,
    )
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


def _types(events: list[TelemetryEvent]) -> list[str]:
    return [type(event).__name__ for event in events]


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
@pytest.mark.parametrize("runtime_backend", _BACKENDS, indirect=True)
def test_runtime_emits_run_and_step_events(
    registry: Registry,
    runner_factory,
    runtime_backend,
) -> None:
    recorder = RecordingTelemetry()

    result = _run(runner_factory(telemetry=(recorder,)), registry)

    assert result["document"]["version"] == "2.0.0"
    assert _types(recorder.events) == [
        "RunStarted",
        "StepStarted",
        "StepCompleted",
        "RunCompleted",
    ]
    started = cast("RunStarted", recorder.events[0])
    assert started.run.run_id
    assert started.plan.path.entries
    step = cast("StepStarted", recorder.events[1]).step
    assert step.name == "migrate_v1_to_v2"
    assert step.source_dataset.version == "1.0.0"
    assert step.target_dataset.version == "2.0.0"
    assert step.target_dataset.fields
    completed = cast("StepCompleted", recorder.events[2])
    assert completed.duration_seconds >= 0
    run_completed = cast("RunCompleted", recorder.events[3])
    assert run_completed.duration_seconds >= 0


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_telemetry_adapter_failures_are_isolated(
    registry: Registry,
    runner_factory,
    caplog,
) -> None:
    recorder = RecordingTelemetry()

    result = _run(
        runner_factory(telemetry=(FailingTelemetry(), recorder)),
        registry,
    )

    assert result["document"]["version"] == "2.0.0"
    assert _types(recorder.events) == [
        "RunStarted",
        "StepStarted",
        "StepCompleted",
        "RunCompleted",
    ]
    assert "telemetry adapter FailingTelemetry failed" in caplog.text


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_otel_adapter_creates_run_and_step_spans(
    registry: Registry,
    runner_factory,
) -> None:
    tracer = RecordingTracer()
    adapter = OtelAdapter(tracer=cast("Any", tracer), service="orders")

    result = _run(runner_factory(telemetry=(adapter,)), registry)

    assert result["document"]["version"] == "2.0.0"
    assert [span.name for span in tracer.spans] == ["orders.run", "orders.migrate"]
    run_span, step_span = tracer.spans
    assert run_span.ended is True
    assert run_span.status == (StatusCode.OK, None)
    assert run_span.attributes["migration.entries"] == 1
    assert step_span.ended is True
    assert step_span.status == (StatusCode.OK, None)
    assert step_span.attributes["migration.source"] == "test:User@1.0.0"
    assert step_span.attributes["migration.target"] == "test:User@2.0.0"
    assert step_span.attributes["migration.duration_seconds"] >= 0


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_openlineage_adapter_emits_run_and_step_events(
    registry: Registry,
    runner_factory,
) -> None:
    client = RecordingLineageClient()
    adapter = OpenLineageAdapter(
        client=client,
        namespace="test",
        producer="tests",
    )

    result = _run(runner_factory(telemetry=(adapter,)), registry)

    assert result["document"]["version"] == "2.0.0"
    assert [event.eventType.value for event in client.events] == [
        "START",
        "START",
        "COMPLETE",
        "COMPLETE",
    ]
    run_started, step_started, step_completed, run_completed = client.events
    assert run_started.job.name == "migration.run"
    assert run_completed.job.name == "migration.run"
    assert step_started.job.name == "migration.User.1.0.0->2.0.0"
    assert step_completed.job.name == "migration.User.1.0.0->2.0.0"
    assert step_started.inputs[0].facets["version"].datasetVersion == "1.0.0"
    assert step_started.outputs[0].facets["version"].datasetVersion == "2.0.0"
    tags = {tag.key: tag.value for tag in step_started.job.facets["tags"].tags}
    assert tags["pyverge.migration.name"] == "migrate_v1_to_v2"
    assert tags["pyverge.migration.discriminator"] == "default"
    assert step_started.run.facets["parent"].run.runId == run_started.run.runId


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_openlineage_namespace_mismatch_is_isolated(
    registry: Registry,
    runner_factory,
    caplog,
) -> None:
    client = RecordingLineageClient()
    adapter = OpenLineageAdapter(
        client=client,
        namespace="other",
        producer="tests",
    )

    result = _run(runner_factory(telemetry=(adapter,)), registry)

    assert result["document"]["version"] == "2.0.0"
    assert client.events == []
    assert "does not match graph namespace" in caplog.text


@pytest.mark.parametrize(
    "model_adapter, registry",
    _FAILING_MODELS,
    indirect=["model_adapter", "registry"],
)
def test_runtime_emits_failed_events(
    registry: Registry,
    runner_factory,
) -> None:
    recorder = RecordingTelemetry()

    with pytest.raises(Exception, match="boom"):
        _run(runner_factory(telemetry=(recorder,)), registry)

    assert _types(recorder.events) == [
        "RunStarted",
        "StepStarted",
        "StepFailed",
        "RunFailed",
    ]
    step_failed = recorder.events[2]
    run_failed = recorder.events[3]
    assert getattr(step_failed, "error") is not None
    assert getattr(run_failed, "error") is not None


@pytest.mark.parametrize(
    "model_adapter, registry",
    _FAILING_MODELS,
    indirect=["model_adapter", "registry"],
)
def test_openlineage_adapter_records_failed_step(
    registry: Registry,
    runner_factory,
) -> None:
    client = RecordingLineageClient()
    adapter = OpenLineageAdapter(
        client=client,
        namespace="test",
        producer="tests",
    )

    with pytest.raises(Exception, match="boom"):
        _run(runner_factory(telemetry=(adapter,)), registry)

    assert [event.eventType.value for event in client.events] == [
        "START",
        "START",
        "FAIL",
        "FAIL",
    ]
    step_failed = client.events[2]
    assert "boom" in step_failed.run.facets["error"].message


@pytest.mark.parametrize(
    "model_adapter, registry",
    _FAILING_MODELS,
    indirect=["model_adapter", "registry"],
)
def test_otel_adapter_records_failed_step(
    registry: Registry,
    runner_factory,
) -> None:
    tracer = RecordingTracer()
    adapter = OtelAdapter(tracer=cast("Any", tracer), service="orders")

    with pytest.raises(Exception, match="boom"):
        _run(runner_factory(telemetry=(adapter,)), registry)

    spans = {span.name: span for span in tracer.spans}
    assert set(spans) == {"orders.run", "orders.migrate"}
    assert spans["orders.migrate"].status[0] == StatusCode.ERROR
    assert spans["orders.run"].status[0] == StatusCode.ERROR
    assert spans["orders.migrate"].exceptions
