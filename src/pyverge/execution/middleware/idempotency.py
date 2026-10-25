from __future__ import annotations

from typing import Any

from .types import IdempotencyKeyFactory, IdempotencyStore


class IdempotencyMiddleware:
    """Cache whole-run results by a caller-provided key."""

    def __init__(
        self,
        *,
        key_factory: IdempotencyKeyFactory,
        store: IdempotencyStore,
    ) -> None:
        self._key_factory = key_factory
        self._store = store

    @property
    def store(self) -> IdempotencyStore:
        return self._store

    def wrap(self, inner: Any) -> Any:
        return _Idempotency(
            inner,
            key_factory=self._key_factory,
            store=self._store,
        )


class _Idempotency:
    def __init__(
        self,
        inner: Any,
        *,
        key_factory: IdempotencyKeyFactory,
        store: IdempotencyStore,
    ) -> None:
        self._inner = inner
        self._key_factory = key_factory
        self._store = store

    def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        key = self._key_factory(plan, payload, run)
        cached = self._store.get(key)
        if cached is not None:
            return cached
        if not self._store.claim(key):
            cached = self._store.get(key)
            if cached is None:
                raise RuntimeError(f"idempotency key {key!r} is claimed")
            return cached
        try:
            result = self._inner.execute(plan, payload, run, adapter)
        except Exception:
            self._store.release(key)
            raise
        if hasattr(result, "__await__"):
            return self._async_result(result, key)
        self._store.complete(key, result)
        return result

    async def _async_result(self, result: Any, key: str) -> Any:
        try:
            value = await result
        except Exception:
            self._store.release(key)
            raise
        self._store.complete(key, value)
        return value


__all__ = ["IdempotencyMiddleware"]
