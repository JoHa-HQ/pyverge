from __future__ import annotations

import inspect
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from pyverge.core.types import MigrationFunc, ModelData


class SyncStepStrategy(Protocol):
    """Execute one sync migration callable."""

    def invoke(
        self,
        func: MigrationFunc,
        data: ModelData,
        context: Mapping[str, object],
    ) -> ModelData: ...


class AsyncStepStrategy(Protocol):
    """Execute one sync or async migration callable from a coroutine."""

    async def invoke(
        self,
        func: MigrationFunc,
        data: ModelData,
        context: Mapping[str, object],
    ) -> ModelData: ...


@dataclass(frozen=True, slots=True)
class ThreadedStrategy:
    """Invoke sync migrations directly in the calling thread."""

    def invoke(
        self,
        func: MigrationFunc,
        data: ModelData,
        context: Mapping[str, object],
    ) -> ModelData:
        return func(data, context)


@dataclass(frozen=True, slots=True)
class ProcessStrategy:
    """Invoke sync migrations in a process pool."""

    executor: ProcessPoolExecutor

    def invoke(
        self,
        func: MigrationFunc,
        data: ModelData,
        context: Mapping[str, object],
    ) -> ModelData:
        return self.executor.submit(func, data, dict(context)).result()


@dataclass(frozen=True, slots=True)
class AsyncStrategy:
    """Invoke sync or async migrations in the current event loop."""

    async def invoke(
        self,
        func: MigrationFunc,
        data: ModelData,
        context: Mapping[str, object],
    ) -> ModelData:
        result = func(data, context)
        if inspect.isawaitable(result):
            return await result
        return result


__all__ = [
    "AsyncStepStrategy",
    "AsyncStrategy",
    "ProcessStrategy",
    "SyncStepStrategy",
    "ThreadedStrategy",
]
