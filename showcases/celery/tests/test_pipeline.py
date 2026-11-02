# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end Celery showcase: a chain across three task versions."""

from __future__ import annotations

from celery_demo.domain import order_v1, order_v2, order_v3
from celery_demo.tasks import build_demo


def test_chain_converges_between_task_versions() -> None:
    demo = build_demo(eager=True)
    try:
        result = demo.run(order_v1())
    finally:
        demo.close()

    assert [name for name, _ in demo.trace] == ["ingest", "enrich", "publish"]
    assert demo.trace[0][1] == order_v1()
    assert demo.trace[1][1] == order_v2()
    assert demo.trace[2][1] == {**order_v3(), "currency": "EUR"}
    assert result == {
        **order_v3(),
        "currency": "EUR",
        "status": "published",
    }


def test_ingest_accepts_a_newer_payload() -> None:
    demo = build_demo(eager=True)
    try:
        result = demo.run(order_v2())
    finally:
        demo.close()

    assert demo.trace[0][1] == order_v1()
    assert result["version"] == "3.0.0"
