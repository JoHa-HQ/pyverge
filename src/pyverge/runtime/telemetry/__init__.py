from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias

if TYPE_CHECKING:
    from pyverge.runtime.context import RunContext, StepContext
    from pyverge.runtime.plan import ExecutionPlan

_LOGGER = logging.getLogger("pyverge.runtime.telemetry")


@dataclass(frozen=True, slots=True)
class RunStarted:
    """Emitted immediately before a run executes."""

    run: RunContext
    plan: ExecutionPlan


@dataclass(frozen=True, slots=True)
class RunCompleted:
    """Emitted after a run completes successfully."""

    run: RunContext
    plan: ExecutionPlan
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class RunFailed:
    """Emitted when a run fails or is cancelled."""

    run: RunContext
    plan: ExecutionPlan
    error: BaseException
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class StepStarted:
    """Emitted immediately before a migration step executes."""

    step: StepContext


@dataclass(frozen=True, slots=True)
class StepCompleted:
    """Emitted after a migration step completes successfully."""

    step: StepContext
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class StepFailed:
    """Emitted when a migration step fails or is cancelled."""

    step: StepContext
    error: BaseException
    duration_seconds: float


TelemetryEvent: TypeAlias = (
    RunStarted | RunCompleted | RunFailed | StepStarted | StepCompleted | StepFailed
)

TelemetryMode: TypeAlias = Literal["all", "errors", "off"]


class TelemetryAdapter(Protocol):
    """Translate runtime lifecycle events into a telemetry backend."""

    def emit(self, event: TelemetryEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class TelemetryPublisher:
    """Best-effort, isolated fan-out to telemetry adapters."""

    adapters: tuple[TelemetryAdapter, ...] = field(default_factory=tuple)
    mode: TelemetryMode = "all"

    @property
    def enabled(self) -> bool:
        """Whether any adapter can receive an event."""
        return bool(self.adapters) and self.mode != "off"

    @property
    def emits_success(self) -> bool:
        """Whether successful lifecycle events should be constructed."""
        return self.enabled and self.mode == "all"

    @property
    def emits_failure(self) -> bool:
        """Whether failed lifecycle events should be constructed."""
        return self.enabled

    def emit(self, event: TelemetryEvent) -> None:
        if not self.enabled:
            return
        if self.mode == "errors" and not isinstance(event, (RunFailed, StepFailed)):
            return
        for adapter in self.adapters:
            try:
                adapter.emit(event)
            except Exception:
                _LOGGER.exception(
                    "telemetry adapter %s failed for %s",
                    type(adapter).__name__,
                    type(event).__name__,
                )


EMPTY_TELEMETRY = TelemetryPublisher()


__all__ = [
    "EMPTY_TELEMETRY",
    "RunCompleted",
    "RunFailed",
    "RunStarted",
    "StepCompleted",
    "StepFailed",
    "StepStarted",
    "TelemetryAdapter",
    "TelemetryEvent",
    "TelemetryMode",
    "TelemetryPublisher",
]
