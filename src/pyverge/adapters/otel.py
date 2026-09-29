from __future__ import annotations

import time
from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any

from opentelemetry.trace import Span, SpanKind, StatusCode, Tracer

from pyverge.core.hooks import MigrationHook
from pyverge.types import Comparable


class OTELHook(MigrationHook):
    """OpenTelemetry hook — creates a span per migration with duration,
    status, and exception recording.
    """

    def __init__(self, *, tracer: Tracer, service: str = "converge") -> None:
        self._tracer = tracer
        self._service = service
        self._span: Span | None = None
        self._scope: AbstractContextManager[Span] | None = None
        self._start_time: float = 0.0

    def before_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
    ) -> None:
        self._start_time = time.perf_counter()
        # ``start_as_current_span`` makes the step span the active span for the
        # duration of the migration, so it nests under any enclosing call span.
        self._scope = self._tracer.start_as_current_span(
            f"{self._service}.migrate",
            kind=SpanKind.INTERNAL,
            attributes={
                "service.name": self._service,
                "migration.kind": str(name),
                "migration.from_version": str(from_version),
                "migration.to_version": str(to_version),
            },
        )
        self._span = self._scope.__enter__()

    def after_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        original_data: Mapping[str, Any],
        migrated_data: Mapping[str, Any],
    ) -> None:
        if self._span is None:
            return
        self._span.set_attribute(
            "migration.duration_seconds",
            time.perf_counter() - self._start_time,
        )
        self._span.set_status(StatusCode.OK)
        self._close()

    def on_error(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
        error: Exception,
    ) -> None:
        if self._span is None:
            return
        self._span.record_exception(error)
        self._span.set_status(StatusCode.ERROR, str(error))
        self._close()

    def _close(self) -> None:
        if self._scope is not None:
            self._scope.__exit__(None, None, None)
        self._scope = None
        self._span = None


__all__ = ["OTELHook"]
