from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from opentelemetry.trace import SpanKind, StatusCode, Tracer

from pyverge.runtime.context import StepContext

from . import (
    RunCompleted,
    RunFailed,
    RunStarted,
    StepCompleted,
    StepFailed,
    StepStarted,
    TelemetryEvent,
)


@dataclass(slots=True)
class _ActiveSpan:
    span: Any
    scope: Any
    started: float


class OtelAdapter:
    """Translate lifecycle events into OpenTelemetry run and step spans."""

    def __init__(self, *, tracer: Tracer, service: str = "converge") -> None:
        self._tracer = tracer
        self._service = service
        self._lock = Lock()
        self._runs: dict[str, _ActiveSpan] = {}
        self._steps: dict[tuple[str, tuple[str | int, ...], int], _ActiveSpan] = {}

    def emit(self, event: TelemetryEvent) -> None:
        if isinstance(event, RunStarted):
            self._start_run(event)
        elif isinstance(event, RunCompleted):
            self._finish_run(event, error=None)
        elif isinstance(event, RunFailed):
            self._finish_run(event, error=event.error)
        elif isinstance(event, StepStarted):
            self._start_step(event)
        elif isinstance(event, StepCompleted):
            self._finish_step(event, error=None)
        elif isinstance(event, StepFailed):
            self._finish_step(event, error=event.error)

    def _start_run(self, event: RunStarted) -> None:
        active = self._enter(
            f"{self._service}.run",
            {
                "service.name": self._service,
                "run.id": event.run.run_id,
                "migration.entries": len(event.plan.path.entries),
            },
        )
        with self._lock:
            self._runs[event.run.run_id] = active

    def _finish_run(
        self,
        event: RunCompleted | RunFailed,
        *,
        error: BaseException | None,
    ) -> None:
        with self._lock:
            active = self._runs.pop(event.run.run_id, None)
        if active is None:
            return
        self._exit(active, duration=event.duration_seconds, error=error)

    def _start_step(self, event: StepStarted) -> None:
        step = event.step
        key = (step.run.run_id, step.path, step.index)
        active = self._enter(f"{self._service}.migrate", self._step_attributes(step))
        with self._lock:
            self._steps[key] = active

    def _finish_step(
        self,
        event: StepCompleted | StepFailed,
        *,
        error: BaseException | None,
    ) -> None:
        step = event.step
        key = (step.run.run_id, step.path, step.index)
        with self._lock:
            active = self._steps.pop(key, None)
        if active is None:
            return
        self._exit(active, duration=event.duration_seconds, error=error)

    def _enter(self, name: str, attributes: dict[str, Any]) -> _ActiveSpan:
        scope = self._tracer.start_as_current_span(
            name,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        )
        started = time.perf_counter()
        if not hasattr(scope, "__enter__"):
            return _ActiveSpan(span=scope, scope=None, started=started)
        return _ActiveSpan(span=scope.__enter__(), scope=scope, started=started)

    def _exit(
        self,
        active: _ActiveSpan,
        *,
        duration: float,
        error: BaseException | None,
    ) -> None:
        active.span.set_attribute("migration.duration_seconds", duration)
        if error is not None:
            active.span.record_exception(error)
            active.span.set_status(StatusCode.ERROR, str(error))
        else:
            active.span.set_status(StatusCode.OK)
        if active.scope is not None:
            active.scope.__exit__(
                type(error) if error is not None else None,
                error,
                error.__traceback__ if error is not None else None,
            )
        else:
            active.span.end()

    def _step_attributes(self, step: StepContext) -> dict[str, Any]:
        attributes = {
            "service.name": self._service,
            "migration.name": step.name,
            "migration.namespace": step.source.namespace,
            "migration.kind": step.source.kind,
            "migration.source": str(step.source),
            "migration.target": str(step.target),
            "migration.from_version": str(step.source),
            "migration.to_version": str(step.target),
            "migration.discriminator": step.edge.discriminator,
        }
        if step.migration is not None:
            attributes["migration.strategy"] = step.migration.strategy
            attributes["migration.identity"] = step.migration.identity
        return attributes


__all__ = ["OtelAdapter"]
