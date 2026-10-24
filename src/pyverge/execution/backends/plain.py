"""Plain concurrency backend: run work in the caller's context."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


class PlainBackend:
    """Run sync work directly and await async work in the current loop."""

    def run(self, work: Callable[..., T], /, *args: Any) -> T:
        return work(*args)

    async def arun(
        self,
        work: Callable[..., Awaitable[T]],
        /,
        *args: Any,
    ) -> T:
        return await work(*args)


__all__ = ["PlainBackend"]
