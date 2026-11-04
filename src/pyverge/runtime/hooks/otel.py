from __future__ import annotations

import time
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from opentelemetry.trace import Span, SpanKind, StatusCode, Tracer

from pyverge.core.types import HookState
from pyverge.runtime.context import StepContext
from pyverge.runtime.hooks.types import HookScope, MigrationHook


@dataclass
class _SpanScope:
    """One OTel span lifetime for one migration step."""

    tracer: Tracer
    service: str
    step: StepContext
    span: Span | None = field(init=False, default=None)
    scope: AbstractContextManager[Span] | None = field(init=False, default=None)
    start_time: float = field(init=False, default=0.0)

    def __enter__(self) -> Span:
        scope = self.tracer.start_as_current_span(
            f"{self.service}.migrate",
            kind=SpanKind.INTERNAL,
            attributes=self._attributes(),
        )
        self.scope = scope
        self.span = scope.__enter__()
        self.start_time = time.perf_counter()
        return self.span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.span is None:
            return
        self.span.set_attribute(
            "migration.duration_seconds",
            time.perf_counter() - self.start_time,
        )
        if exc is not None:
            self.span.record_exception(exc)
            self.span.set_status(StatusCode.ERROR, str(exc))
        else:
            self.span.set_status(StatusCode.OK)
        if self.scope is not None:
            self.scope.__exit__(exc_type, exc, traceback)

    def _attributes(self) -> dict[str, Any]:
        attributes = {
            "service.name": self.service,
            "migration.name": self.step.name,
            "migration.namespace": self.step.source.namespace,
            "migration.kind": self.step.source.kind,
            "migration.source": str(self.step.source),
            "migration.target": str(self.step.target),
            "migration.from_version": str(self.step.source),
            "migration.to_version": str(self.step.target),
            "migration.discriminator": self.step.edge.discriminator,
        }
        if self.step.migration is not None:
            attributes["migration.strategy"] = self.step.migration.strategy
            attributes["migration.identity"] = self.step.migration.identity
        return attributes


class OTELHook(MigrationHook):
    """Create one OTel span per migration edge."""

    def __init__(self, *, tracer: Tracer, service: str = "converge") -> None:
        self._tracer = tracer
        self._service = service

    def before_migrate(
        self,
        step: StepContext,
        data: Mapping[str, Any],
        *,
        state: HookState,
    ) -> HookScope:
        return _SpanScope(self._tracer, self._service, step)

    def after_migrate(
        self,
        step: StepContext,
        original_data: Mapping[str, Any],
        migrated_data: Mapping[str, Any],
        *,
        state: HookState,
    ) -> None:
        return None

    def on_error(
        self,
        step: StepContext,
        data: Mapping[str, Any],
        error: Exception,
        *,
        state: HookState,
    ) -> None:
        return None


__all__ = ["OTELHook"]
