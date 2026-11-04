"""Celery target selection."""

from __future__ import annotations

from collections.abc import Mapping

from pyverge.core.graph.planning.targets import DefaultTarget, FirstMatch
from pyverge.runtime.manager.types import TargetPolicy

from .domain import TaskContext


class HeaderTarget:
    """Select the target from a task header."""

    def __init__(self, header: str) -> None:
        self._header = header

    def select(self, context: TaskContext) -> TargetPolicy | None:
        value = context.header(self._header)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode()
        return str(value)


class TaskTarget:
    """Select a target configured for the task name."""

    def __init__(self, targets: Mapping[str, TargetPolicy]) -> None:
        self._targets = dict(targets)

    def select(self, context: TaskContext) -> TargetPolicy | None:
        return self._targets.get(context.name)


class QueueTarget:
    """Select a target configured for the queue."""

    def __init__(self, targets: Mapping[str, TargetPolicy]) -> None:
        self._targets = dict(targets)

    def select(self, context: TaskContext) -> TargetPolicy | None:
        if context.queue is None:
            return None
        return self._targets.get(context.queue)


class TaskTargets:
    """Header -> task -> queue -> default target chain."""

    def __init__(
        self,
        default: TargetPolicy,
        *,
        header: str | None = None,
        by_task: Mapping[str, TargetPolicy] | None = None,
        by_queue: Mapping[str, TargetPolicy] | None = None,
    ) -> None:
        selectors = []
        if header is not None:
            selectors.append(HeaderTarget(header))
        if by_task:
            selectors.append(TaskTarget(by_task))
        if by_queue:
            selectors.append(QueueTarget(by_queue))
        selectors.append(DefaultTarget(default))
        self._chain = FirstMatch(*selectors)
        self._default = default

    def select(self, context: TaskContext) -> TargetPolicy:
        """Return the selected target, falling back to the default."""
        target = self._chain.select(context)
        return self._default if target is None else target


__all__ = [
    "HeaderTarget",
    "QueueTarget",
    "TaskTarget",
    "TaskTargets",
]
