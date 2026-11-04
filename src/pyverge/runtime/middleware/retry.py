from __future__ import annotations

from typing import Any

from tenacity import AsyncRetrying, Retrying, stop_after_attempt


class RetryMiddleware:
    """Retry the entire backend execute call."""

    def __init__(self, attempts: int) -> None:
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        self._attempts = attempts

    def wrap(self, inner: Any) -> Any:
        return _Retry(inner, attempts=self._attempts)


class _Retry:
    def __init__(self, inner: Any, *, attempts: int) -> None:
        self._inner = inner
        self._attempts = attempts

    def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        for attempt in Retrying(
            stop=stop_after_attempt(self._attempts),
            reraise=True,
        ):
            with attempt:
                result = self._inner.execute(plan, payload, run, adapter)
                if hasattr(result, "__await__"):
                    return self._async_execute(plan, payload, run, adapter)
                return result
        raise AssertionError("unreachable")

    async def _async_execute(
        self, plan: Any, payload: Any, run: Any, adapter: Any
    ) -> Any:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._attempts),
            reraise=True,
        ):
            with attempt:
                return await self._inner.execute(plan, payload, run, adapter)
        raise AssertionError("unreachable")


__all__ = ["RetryMiddleware"]
