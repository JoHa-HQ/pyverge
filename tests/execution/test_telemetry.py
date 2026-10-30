"""Telemetry hook and middleware behaviour."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

from opentelemetry.trace import StatusCode

from pyverge.execution.hooks import OpenLineageHook, OTELHook
from pyverge.execution.hooks.state import new_hook_state
from pyverge.execution.middleware import OpenLineageMiddleware, OtelMiddleware
from pyverge.versioning import MigrationDescriptor, NodeId


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


def _node(version: str) -> NodeId:
    return NodeId.parse("com.acme.orders", "User", version)


def test_otel_hook_keeps_interleaved_step_state_separate() -> None:
    tracer = RecordingTracer()
    hook = OTELHook(tracer=cast("Any", tracer), service="orders")
    state = new_hook_state()
    v1, v2, v3 = _node("1.0.0"), _node("2.0.0"), _node("3.0.0")

    hook.before_migrate("one_to_two", v1, v2, {}, state=state)
    hook.before_migrate("two_to_three", v2, v3, {}, state=state)
    hook.after_migrate("two_to_three", v2, v3, {}, {}, state=state)
    hook.after_migrate("one_to_two", v1, v2, {}, {}, state=state)

    first, second = tracer.spans
    assert first.attributes["migration.source"] == "com.acme.orders:User@1.0.0"
    assert first.attributes["migration.target"] == "com.acme.orders:User@2.0.0"
    assert first.attributes["migration.namespace"] == "com.acme.orders"
    assert first.attributes["migration.kind"] == "User"
    assert second.attributes["migration.source"] == "com.acme.orders:User@2.0.0"
    assert first.ended is True
    assert second.ended is True
    assert first.status == (StatusCode.OK, None)
    assert second.status == (StatusCode.OK, None)


def test_otel_hook_reports_migration_descriptor() -> None:
    tracer = RecordingTracer()
    hook = OTELHook(tracer=cast("Any", tracer), service="orders")
    state = new_hook_state()
    v1, v2 = _node("1.0.0"), _node("2.0.0")
    descriptor = MigrationDescriptor("jsonpatch", "docs.user.v1_v2")

    hook.before_migrate(
        "one_to_two",
        v1,
        v2,
        {},
        migration=descriptor,
        state=state,
    )
    hook.after_migrate(
        "one_to_two",
        v1,
        v2,
        {},
        {},
        migration=descriptor,
        state=state,
    )

    attributes = tracer.spans[0].attributes
    assert attributes["migration.strategy"] == "jsonpatch"
    assert attributes["migration.identity"] == "docs.user.v1_v2"


def test_otel_hook_records_error_for_matching_step() -> None:
    tracer = RecordingTracer()
    hook = OTELHook(tracer=cast("Any", tracer), service="orders")
    state = new_hook_state()
    v1, v2 = _node("1.0.0"), _node("2.0.0")
    error = RuntimeError("boom")

    hook.before_migrate("one_to_two", v1, v2, {}, state=state)
    hook.on_error("one_to_two", v1, v2, {}, error, state=state)

    span = tracer.spans[0]
    assert span.exceptions == [error]
    assert span.status == (StatusCode.ERROR, "boom")
    assert span.ended is True


def test_openlineage_hook_keeps_interleaved_run_ids_separate() -> None:
    client = RecordingLineageClient()
    hook = OpenLineageHook(
        client=client,
        namespace="com.acme.orders",
        producer="tests",
    )
    state = new_hook_state()
    v1, v2, v3 = _node("1.0.0"), _node("2.0.0"), _node("3.0.0")

    hook.before_migrate("one_to_two", v1, v2, {}, state=state)
    hook.before_migrate("two_to_three", v2, v3, {}, state=state)
    hook.after_migrate("two_to_three", v2, v3, {}, {}, state=state)
    hook.after_migrate("one_to_two", v1, v2, {}, {}, state=state)

    started = [event for event in client.events if event.eventType.value == "START"]
    completed = [
        event for event in client.events if event.eventType.value == "COMPLETE"
    ]
    assert len(started) == 2  # noqa: PLR2004
    assert len(completed) == 2  # noqa: PLR2004

    started_by_job = {event.job.name: event for event in started}
    completed_by_job = {event.job.name: event for event in completed}
    assert set(started_by_job) == {
        "migration.User.1.0.0->2.0.0",
        "migration.User.2.0.0->3.0.0",
    }
    for job_name, started_event in started_by_job.items():
        assert completed_by_job[job_name].run.runId == started_event.run.runId


def test_openlineage_middleware_validates_graph_namespace() -> None:
    client = RecordingLineageClient()
    middleware = OpenLineageMiddleware(
        client=client,
        namespace="com.acme.billing",
        producer="tests",
    )
    entry = SimpleNamespace(source=_node("1.0.0"), target=_node("2.0.0"))
    plan = SimpleNamespace(path=SimpleNamespace(entries=(entry,)))
    wrapped = middleware.wrap(_AsyncInner())

    try:
        wrapped.execute(plan, {}, SimpleNamespace(run_id="run-1"), None)
    except ValueError as error:
        assert "does not match graph namespace" in str(error)
    else:
        raise AssertionError("expected namespace validation error")


class _AsyncInner:
    async def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        await asyncio.sleep(0)
        return {"ok": True}


def test_otel_middleware_keeps_async_span_open_until_completion() -> None:
    tracer = RecordingTracer()
    middleware = OtelMiddleware(tracer=cast("Any", tracer), service="orders")
    wrapped = middleware.wrap(_AsyncInner())
    plan = SimpleNamespace(path=SimpleNamespace(entries=()))
    run = SimpleNamespace(run_id="run-1")

    pending = wrapped.execute(plan, {}, run, None)
    span = tracer.spans[0]

    assert span.ended is False
    result = asyncio.run(pending)

    assert result == {"ok": True}
    assert span.ended is True
    assert span.status == (StatusCode.OK, None)
