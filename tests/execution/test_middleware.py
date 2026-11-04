# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Execution middleware tests."""

from __future__ import annotations

import asyncio

import pytest

from pyverge.runtime.context import MigrationContext
from pyverge.runtime.middleware import (
    AuditMiddleware,
    IdempotencyMiddleware,
    RetryMiddleware,
    TransactionMiddleware,
)
from tests.utils.middleware import (
    AsyncScriptedBackend,
    FakeIdempotencyStore,
    FakeTransactionManager,
    OrderMiddleware,
    RecordingAuditSink,
    ScriptedBackend,
)


@pytest.mark.parametrize(
    "execution_runner",
    [
        pytest.param(
            (ScriptedBackend, 0, (AuditMiddleware(RecordingAuditSink()),)),
            id="audit",
        )
    ],
    indirect=True,
)
def test_audit_middleware_records_success(execution_runner, plan) -> None:
    execution_runner.execute(plan, context=MigrationContext.empty())

    assert [event.status for event in execution_runner.middleware[0].sink.events] == [
        "started",
        "completed",
    ]


@pytest.mark.parametrize(
    "execution_runner",
    [
        pytest.param(
            (ScriptedBackend, 1, (AuditMiddleware(RecordingAuditSink()),)),
            id="audit",
        )
    ],
    indirect=True,
)
def test_audit_middleware_records_failure(execution_runner, plan) -> None:
    with pytest.raises(RuntimeError):
        execution_runner.execute(plan, context=MigrationContext.empty())

    assert [event.status for event in execution_runner.middleware[0].sink.events] == [
        "started",
        "failed",
    ]


@pytest.mark.parametrize(
    "execution_runner",
    [
        pytest.param(
            (
                ScriptedBackend,
                0,
                (TransactionMiddleware(FakeTransactionManager()),),
            ),
            id="transaction",
        )
    ],
    indirect=True,
)
def test_transaction_middleware_commits(execution_runner, plan) -> None:
    execution_runner.execute(plan, context=MigrationContext.empty())

    assert execution_runner.middleware[0].manager.tx.committed


@pytest.mark.parametrize(
    "execution_runner",
    [
        pytest.param(
            (
                ScriptedBackend,
                1,
                (TransactionMiddleware(FakeTransactionManager()),),
            ),
            id="transaction",
        )
    ],
    indirect=True,
)
def test_transaction_middleware_rolls_back(execution_runner, plan) -> None:
    with pytest.raises(RuntimeError):
        execution_runner.execute(plan, context=MigrationContext.empty())

    assert execution_runner.middleware[0].manager.tx.rolled_back


@pytest.mark.parametrize(
    "execution_runner",
    [
        pytest.param(
            (ScriptedBackend, 2, (RetryMiddleware(3),)),
            id="retry-3",
        )
    ],
    indirect=True,
)
def test_retry_middleware_retries_sync(execution_runner, plan) -> None:
    assert execution_runner.execute(plan, context=MigrationContext.empty()) == {
        "ok": True
    }
    assert execution_runner.backend.calls == 3  # noqa: PLR2004


@pytest.mark.parametrize(
    "async_execution_runner",
    [
        pytest.param(
            (AsyncScriptedBackend, 2, (RetryMiddleware(3),)),
            id="retry-3",
        )
    ],
    indirect=True,
)
def test_retry_middleware_retries_async(async_execution_runner, plan) -> None:
    assert asyncio.run(
        async_execution_runner.execute(plan, context=MigrationContext.empty())
    ) == {"ok": True}
    assert async_execution_runner.backend.calls == 3  # noqa: PLR2004


@pytest.mark.parametrize(
    "execution_runner",
    [
        pytest.param(
            (
                ScriptedBackend,
                0,
                (
                    IdempotencyMiddleware(
                        key_factory=lambda plan, payload, run: "key",
                        store=FakeIdempotencyStore(),
                    ),
                ),
            ),
            id="idempotency",
        )
    ],
    indirect=True,
)
def test_idempotency_middleware_caches_result(execution_runner, plan) -> None:
    execution_runner.execute(plan, context=MigrationContext.empty())
    execution_runner.execute(plan, context=MigrationContext.empty())

    assert execution_runner.middleware[0].store.values["key"] == {"ok": True}


@pytest.mark.parametrize(
    "execution_runner",
    [
        pytest.param(
            (
                ScriptedBackend,
                1,
                (
                    IdempotencyMiddleware(
                        key_factory=lambda plan, payload, run: "key",
                        store=FakeIdempotencyStore(),
                    ),
                ),
            ),
            id="idempotency",
        )
    ],
    indirect=True,
)
def test_idempotency_middleware_releases_on_failure(execution_runner, plan) -> None:
    with pytest.raises(RuntimeError):
        execution_runner.execute(plan, context=MigrationContext.empty())

    assert execution_runner.middleware[0].store.released == ["key"]


@pytest.mark.parametrize(
    "execution_runner",
    [
        pytest.param(
            (
                ScriptedBackend,
                0,
                (
                    OrderMiddleware("outer", log := []),
                    OrderMiddleware("inner", log),
                ),
            ),
            id="outer-inner",
        )
    ],
    indirect=True,
)
def test_middleware_chain_is_onion(execution_runner, plan) -> None:
    execution_runner.execute(plan, context=MigrationContext.empty())

    assert execution_runner.middleware[0].log == [
        "outer:before",
        "inner:before",
        "inner:after",
        "outer:after",
    ]
