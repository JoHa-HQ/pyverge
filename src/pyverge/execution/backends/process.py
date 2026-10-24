"""Process concurrency backend for isolated sync work."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from concurrent.futures import ProcessPoolExecutor
from typing import Any, TypeVar, cast

T = TypeVar("T")


def _invoke(work: Callable[..., T], args: tuple[Any, ...]) -> T:
    return work(*args)


class ProcessBackend:
    """Run sync work in a process pool.

    Callables and arguments must be picklable: module-level migration functions
    work; lambdas and local closures do not.
    """

    def __init__(self, max_workers: int) -> None:
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

    def run(self, work: Callable[..., T], /, *args: Any) -> T:
        return cast("T", self._executor.submit(_invoke, work, args).result())

    async def arun(
        self,
        work: Callable[..., Awaitable[T]],
        /,
        *args: Any,
    ) -> T:
        raise NotImplementedError("ProcessBackend supports sync work only")

    def close(self) -> None:
        self._executor.shutdown()


__all__ = ["ProcessBackend"]
