# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Middleware test doubles."""

from __future__ import annotations

from typing import Any

from pyverge.execution.middleware import AuditEvent


class ScriptedBackend:
    def __init__(self, failures: int = 0) -> None:
        self.calls = 0
        self._failures = failures

    def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        self.calls += 1
        if self.calls <= self._failures:
            raise RuntimeError("boom")
        return {"ok": True}


class AsyncScriptedBackend:
    def __init__(self, failures: int = 0) -> None:
        self.calls = 0
        self._failures = failures

    async def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        self.calls += 1
        if self.calls <= self._failures:
            raise RuntimeError("boom")
        return {"ok": True}


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class FakeTransaction:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self, error: BaseException) -> None:
        self.rolled_back = True


class FakeTransactionManager:
    def __init__(self) -> None:
        self.tx = FakeTransaction()

    def begin(self, plan: Any, payload: Any, run: Any) -> FakeTransaction:
        return self.tx


class FakeIdempotencyStore:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.claimed: set[str] = set()
        self.released: list[str] = []

    def get(self, key: str) -> Any | None:
        return self.values.get(key)

    def claim(self, key: str) -> bool:
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    def complete(self, key: str, result: Any) -> None:
        self.values[key] = result

    def release(self, key: str) -> None:
        self.released.append(key)


class FakeSpan:
    def __init__(self) -> None:
        self.status: Any = None

    def set_status(self, status: Any) -> None:
        self.status = status

    def record_exception(self, error: BaseException) -> None:
        return None


class FakeScope:
    def __init__(self, span: FakeSpan) -> None:
        self._span = span

    def __enter__(self) -> FakeSpan:
        return self._span

    def __exit__(self, *exc_info: Any) -> None:
        return None


class FakeTracer:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.span = FakeSpan()

    def start_as_current_span(self, name: str, **attributes: Any) -> FakeScope:
        self.names.append(name)
        return FakeScope(self.span)


class FakeLineageClient:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def emit(self, event: tuple[str, Any]) -> None:
        self.events.append(event)


class OrderMiddleware:
    """Record onion order for middleware composition tests."""

    def __init__(self, name: str, log: list[str]) -> None:
        self._name = name
        self._log = log

    @property
    def log(self) -> list[str]:
        return self._log

    def wrap(self, inner: Any) -> Any:
        return _Ordered(inner, name=self._name, log=self._log)


class _Ordered:
    def __init__(self, inner: Any, *, name: str, log: list[str]) -> None:
        self._inner = inner
        self._name = name
        self._log = log

    def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        self._log.append(f"{self._name}:before")
        result = self._inner.execute(plan, payload, run, adapter)
        self._log.append(f"{self._name}:after")
        return result
