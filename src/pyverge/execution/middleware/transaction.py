"""Whole-run transaction middleware."""

from __future__ import annotations

from typing import Any

from .types import TransactionManager


class TransactionMiddleware:
    """Wrap the whole backend execution in a transaction."""

    def __init__(self, manager: TransactionManager) -> None:
        self._manager = manager

    @property
    def manager(self) -> TransactionManager:
        return self._manager

    def wrap(self, inner: Any) -> Any:
        return _Transaction(inner, manager=self._manager)


class _Transaction:
    def __init__(self, inner: Any, *, manager: TransactionManager) -> None:
        self._inner = inner
        self._manager = manager

    def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        transaction = self._manager.begin(plan, payload, run)
        try:
            result = self._inner.execute(plan, payload, run, adapter)
        except Exception as error:
            transaction.rollback(error)
            raise
        if hasattr(result, "__await__"):
            return self._async_result(result, transaction)
        transaction.commit()
        return result

    async def _async_result(self, result: Any, transaction: Any) -> Any:
        try:
            value = await result
        except Exception as error:
            transaction.rollback(error)
            raise
        transaction.commit()
        return value


__all__ = ["TransactionMiddleware"]
