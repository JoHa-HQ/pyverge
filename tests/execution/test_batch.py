# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Batch execution keeps per-payload run semantics."""

from __future__ import annotations

import pytest
import semver

from pyverge.core.registry import Registry
from pyverge.runtime.telemetry import RunStarted, TelemetryEvent
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2

_MODELS = [
    [
        PydanticModelAdapter,
        [
            semver.Version,
            "test",
            [UserV1, UserV2],
            [((UserV1, UserV2), migrate_v1_to_v2)],
        ],
    ]
]


class RecordingTelemetry:
    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []

    def emit(self, event: TelemetryEvent) -> None:
        self.events.append(event)


def _payload() -> dict:
    return {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@b.c",
            "role": "user",
        }
    }


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_run_many_uses_independent_runs(registry: Registry, runner_factory) -> None:
    recorder = RecordingTelemetry()
    runner = runner_factory(plan_cache_size=2, telemetry=(recorder,))
    payloads = [_payload(), _payload()]

    results = runner.run_many(
        payloads,
        "latest",
        source_model=None,
        max_depth=-1,
        context=None,
    )

    assert [result["document"]["version"] for result in results] == [
        "2.0.0",
        "2.0.0",
    ]
    run_ids = [
        event.run.run_id
        for event in recorder.events
        if isinstance(event, RunStarted)
    ]
    assert len(run_ids) == 2  # noqa: PLR2004
    assert len(set(run_ids)) == 2  # noqa: PLR2004
    assert "age" not in payloads[0]["document"]
    assert "age" not in payloads[1]["document"]
