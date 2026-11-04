# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import semver

from pyverge.core.graph import MemoryGraphStore, RevisionConflictError
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import UserV1, UserV2, UserV3


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", [UserV1, UserV2], []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_memory_store_generation_and_load(engine) -> None:
    times = iter(
        [
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 2, tzinfo=UTC),
        ]
    )
    store = MemoryGraphStore(clock=lambda: next(times))
    graph = engine.snapshot()

    assert store.load() is None
    first = store.save(graph)
    second = store.save(graph)

    assert first.generation == 1
    assert second.generation == 2  # noqa: PLR2004
    assert first.generated_at < second.generated_at
    assert first.revision == graph.revision
    assert store.load() is graph


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", [UserV1, UserV2], []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_memory_store_rejects_stale_revision(engine) -> None:
    store = MemoryGraphStore()
    store.save(engine.snapshot())
    engine.store_model(UserV3)
    newer = engine.snapshot()

    with pytest.raises(RevisionConflictError):
        store.save(newer, expected_revision=newer.revision)


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", [UserV1, UserV2], []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_memory_store_rejects_stale_generation(engine) -> None:
    store = MemoryGraphStore()
    graph = engine.snapshot()
    store.save(graph)

    with pytest.raises(RevisionConflictError):
        store.save(graph, expected_generation=0)
