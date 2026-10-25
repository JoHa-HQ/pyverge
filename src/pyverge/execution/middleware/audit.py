"""Whole-run audit middleware."""

from __future__ import annotations

import time
from typing import Any

from .types import AuditEvent, AuditSink


class AuditMiddleware:
    """Record start, success, and failure for every run."""

    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    @property
    def sink(self) -> AuditSink:
        return self._sink

    def wrap(self, inner: Any) -> Any:
        return _Audit(inner, sink=self._sink)


class _Audit:
    def __init__(self, inner: Any, *, sink: AuditSink) -> None:
        self._inner = inner
        self._sink = sink

    def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        started = time.perf_counter()
        self._sink.record(
            AuditEvent(
                name="run",
                run_id=run.run_id,
                status="started",
                duration_seconds=None,
                entries=len(plan.path.entries),
                backend=type(self._inner).__name__,
                error=None,
            )
        )
        try:
            result = self._inner.execute(plan, payload, run, adapter)
        except Exception as error:
            self._sink.record(
                AuditEvent(
                    name="run",
                    run_id=run.run_id,
                    status="failed",
                    duration_seconds=time.perf_counter() - started,
                    entries=len(plan.path.entries),
                    backend=type(self._inner).__name__,
                    error=str(error),
                )
            )
            raise
        if hasattr(result, "__await__"):
            return self._async_result(
                result,
                run_id=run.run_id,
                entries=len(plan.path.entries),
                started=started,
            )
        self._sink.record(
            AuditEvent(
                name="run",
                run_id=run.run_id,
                status="completed",
                duration_seconds=time.perf_counter() - started,
                entries=len(plan.path.entries),
                backend=type(self._inner).__name__,
                error=None,
            )
        )
        return result

    async def _async_result(
        self,
        result: Any,
        *,
        run_id: str,
        entries: int,
        started: float,
    ) -> Any:
        try:
            value = await result
        except Exception as error:
            self._sink.record(
                AuditEvent(
                    name="run",
                    run_id=run_id,
                    status="failed",
                    duration_seconds=time.perf_counter() - started,
                    entries=entries,
                    backend=type(self._inner).__name__,
                    error=str(error),
                )
            )
            raise
        self._sink.record(
            AuditEvent(
                name="run",
                run_id=run_id,
                status="completed",
                duration_seconds=time.perf_counter() - started,
                entries=entries,
                backend=type(self._inner).__name__,
                error=None,
            )
        )
        return value


__all__ = ["AuditMiddleware"]
