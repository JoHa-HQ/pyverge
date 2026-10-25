from __future__ import annotations

from typing import Any

from opentelemetry.trace import SpanKind, StatusCode, Tracer


class OtelMiddleware:
    """Control middleware: one span per full migration run."""

    def __init__(self, *, tracer: Tracer, service: str = "converge") -> None:
        self._tracer = tracer
        self._service = service

    @property
    def tracer(self) -> Tracer:
        return self._tracer

    def wrap(self, inner: Any) -> Any:
        return _OtelRun(inner, tracer=self._tracer, service=self._service)


class _OtelRun:
    def __init__(self, inner: Any, *, tracer: Tracer, service: str) -> None:
        self._inner = inner
        self._tracer = tracer
        self._service = service

    def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        span = self._tracer.start_as_current_span(
            f"{self._service}.run",
            kind=SpanKind.INTERNAL,
            attributes={
                "service.name": self._service,
                "run.id": run.run_id,
                "migration.entries": len(plan.path.entries),
            },
        )
        if not hasattr(span, "__enter__"):
            return self._inner.execute(plan, payload, run, adapter)
        with span as active:
            try:
                result = self._inner.execute(plan, payload, run, adapter)
            except Exception as error:
                active.record_exception(error)
                active.set_status(StatusCode.ERROR, str(error))
                raise
            if hasattr(result, "__await__"):
                return self._async_result(result, active)
            active.set_status(StatusCode.OK)
            return result

    async def _async_result(self, result: Any, span: Any) -> Any:
        try:
            value = await result
        except Exception as error:
            span.record_exception(error)
            span.set_status(StatusCode.ERROR, str(error))
            raise
        span.set_status(StatusCode.OK)
        return value


__all__ = ["OtelMiddleware"]
