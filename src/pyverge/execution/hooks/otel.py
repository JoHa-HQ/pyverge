from __future__ import annotations

import time
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from opentelemetry.trace import Span, SpanKind, StatusCode, Tracer

from pyverge.core.types import HookState
from pyverge.execution.hooks.state import pop_state, push_state
from pyverge.execution.hooks.types import MigrationHook
from pyverge.versioning import MigrationDescriptor, NodeId


@dataclass(frozen=True, slots=True)
class _SpanState:
    scope: AbstractContextManager[Span]
    span: Span
    start_time: float


class OTELHook(MigrationHook):
    """Create one OTel span per migration edge."""

    def __init__(self, *, tracer: Tracer, service: str = "converge") -> None:
        self._tracer = tracer
        self._service = service

    def before_migrate(  # noqa: PLR0913
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        data: Mapping[str, Any],
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None:
        scope = self._tracer.start_as_current_span(
            f"{self._service}.migrate",
            kind=SpanKind.INTERNAL,
            attributes=self._attributes(name, from_version, to_version, migration),
        )
        push_state(
            state,
            id(self),
            _SpanState(
                scope=scope,
                span=scope.__enter__(),
                start_time=time.perf_counter(),
            ),
        )

    def after_migrate(  # noqa: PLR0913
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        original_data: Mapping[str, Any],
        migrated_data: Mapping[str, Any],
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None:
        run_state = pop_state(state, id(self))
        if not isinstance(run_state, _SpanState):
            return
        run_state.span.set_attribute(
            "migration.duration_seconds",
            time.perf_counter() - run_state.start_time,
        )
        run_state.span.set_status(StatusCode.OK)
        self._close(run_state)

    def on_error(  # noqa: PLR0913
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        data: Mapping[str, Any],
        error: Exception,
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None:
        run_state = pop_state(state, id(self))
        if not isinstance(run_state, _SpanState):
            return
        run_state.span.record_exception(error)
        run_state.span.set_status(StatusCode.ERROR, str(error))
        self._close(run_state)

    def _attributes(
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        migration: MigrationDescriptor | None,
    ) -> dict[str, Any]:
        attributes = {
            "service.name": self._service,
            "migration.name": str(name),
            "migration.namespace": from_version.namespace,
            "migration.kind": from_version.kind,
            "migration.source": str(from_version),
            "migration.target": str(to_version),
            "migration.from_version": str(from_version),
            "migration.to_version": str(to_version),
        }
        if migration is not None:
            attributes["migration.strategy"] = migration.strategy
            attributes["migration.identity"] = migration.identity
        return attributes

    @staticmethod
    def _close(state: _SpanState) -> None:
        state.scope.__exit__(None, None, None)


__all__ = ["OTELHook"]
