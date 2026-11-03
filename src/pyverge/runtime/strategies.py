from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

from pyverge.core.types import ModelData
from pyverge.runtime.context import StepContext
from pyverge.runtime.plan import ExecutionEntry


def _run_in_process(
    work: Any, data: ModelData, context: Mapping[str, Any]
) -> ModelData:
    return work(data, dict(context))


@dataclass(frozen=True, slots=True)
class ThreadedStrategy:
    """Invoke sync migrations directly in the calling thread."""

    def invoke(
        self,
        entry: ExecutionEntry,
        index: int,
        data: ModelData,
        step: StepContext,
    ) -> ModelData:
        return entry.invoke_migration(index, data, step.view)


@dataclass(frozen=True, slots=True)
class ProcessStrategy:
    """Invoke sync migrations in a process pool."""

    executor: ProcessPoolExecutor

    def invoke(
        self,
        entry: ExecutionEntry,
        index: int,
        data: ModelData,
        step: StepContext,
    ) -> ModelData:
        try:
            return self.executor.submit(
                _run_in_process,
                entry.migration_func(index),
                data,
                dict(step.view),
            ).result()
        except Exception as exc:
            raise entry.migration_error(exc) from exc


@dataclass(frozen=True, slots=True)
class AsyncStrategy:
    """Invoke sync or async migrations in the current event loop."""

    async def invoke(
        self,
        entry: ExecutionEntry,
        index: int,
        data: ModelData,
        step: StepContext,
    ) -> ModelData:
        return await entry.invoke_migration_async(index, data, step.view)


__all__ = [
    "AsyncStrategy",
    "ProcessStrategy",
    "ThreadedStrategy",
]
