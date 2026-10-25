"""Execution middleware contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class BackendMiddleware(Protocol):
    """Wrap one execution backend with cross-cutting behavior."""

    def wrap(self, inner: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One audit record for a migration run."""

    name: str
    run_id: str
    status: str
    duration_seconds: float | None
    entries: int
    backend: str
    error: str | None


class AuditSink(Protocol):
    """Persist audit events."""

    def record(self, event: AuditEvent) -> None: ...


class Transaction(Protocol):
    """One whole-run transaction."""

    def commit(self) -> None: ...
    def rollback(self, error: BaseException) -> None: ...


class TransactionManager(Protocol):
    """Open a whole-run transaction."""

    def begin(self, plan: Any, payload: dict[str, Any], run: Any) -> Transaction: ...


class IdempotencyStore(Protocol):
    """Whole-run idempotency store."""

    def get(self, key: str) -> Any | None: ...
    def claim(self, key: str) -> bool: ...
    def complete(self, key: str, result: Any) -> None: ...
    def release(self, key: str) -> None: ...


class IdempotencyKeyFactory(Protocol):
    """Build a stable key for a whole migration run."""

    def __call__(self, plan: Any, payload: dict[str, Any], run: Any) -> str: ...


__all__ = [
    "AuditEvent",
    "AuditSink",
    "BackendMiddleware",
    "IdempotencyKeyFactory",
    "IdempotencyStore",
    "Transaction",
    "TransactionManager",
]
