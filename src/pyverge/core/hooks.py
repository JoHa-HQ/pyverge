"""Migration hooks for observability and custom behavior."""

import time
from collections.abc import Mapping
from typing import Any

from opentelemetry.trace import Span, SpanKind, StatusCode, Tracer

from .types import Comparable


class MigrationHook:
    """Base class for migration hooks.

    Hooks are read-only observers that allow you to inject custom behavior
    before, after, or on error during migrations.  Default implementations
    are no-ops — subclass and override only what you need.
    """

    def before_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
    ) -> None: ...

    def after_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        original_data: Mapping[str, Any],
        migrated_data: Mapping[str, Any],
    ) -> None: ...

    def on_error(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
        error: Exception,
    ) -> None: ...


class OTELHook(MigrationHook):
    """OpenTelemetry hook — creates a span per migration with duration,
    status, and exception recording.

    Example:
        ```python
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, OTLPSpanExporter

        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

        hook = OTELHook(tracer=trace.get_tracer("converge"), service="converge")
        ```
    """

    def __init__(self, *, tracer: Tracer, service: str = "converge") -> None:
        self._tracer = tracer
        self._service = service
        self._span: Span | None = None
        self._start_time: float = 0.0

    def before_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
    ) -> None:
        self._start_time = time.perf_counter()
        self._span = self._tracer.start_span(
            f"{self._service}.migrate",
            kind=SpanKind.INTERNAL,
            attributes={
                "service.name": self._service,
                "migration.kind": str(name),
                "migration.from_version": str(from_version),
                "migration.to_version": str(to_version),
            },
        )

    def after_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        original_data: Mapping[str, Any],
        migrated_data: Mapping[str, Any],
    ) -> None:
        if self._span is not None:
            self._span.set_attribute(
                "migration.duration_seconds",
                time.perf_counter() - self._start_time,
            )
            self._span.set_status(StatusCode.OK)
            self._span.end()
            self._span = None

    def on_error(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
        error: Exception,
    ) -> None:
        if self._span is not None:
            self._span.record_exception(error)
            self._span.set_status(StatusCode.ERROR, str(error))
            self._span.end()
            self._span = None
