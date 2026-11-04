# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import semver

from pyverge.core.graph import IgraphBackend, RustworkxBackend
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
)

FACTORIES: list[tuple[str, Callable[..., Any] | None]] = [
    ("indexed", None),
    ("rustworkx", RustworkxBackend.build),
    ("igraph", IgraphBackend.build),
]


@pytest.mark.parametrize(("backend_name", "factory"), FACTORIES)
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2, UserV3],
                [
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_backend_conformance(
    backend_name: str,
    factory: Callable[..., Any] | None,
    engine,
) -> None:
    if factory is not None:
        pytest.importorskip(backend_name)
    default = engine.snapshot()
    graph = engine.snapshot(backend_factory=factory)
    v1, v2, v3 = default.kind_versions("User")

    assert graph.revision == default.revision
    assert graph.manifest_digest() == default.manifest_digest()
    assert graph.backend.neighbors(v1, direction="out") == (v2.id,)
    assert graph.backend.neighbors(v2, direction="in") == (v1.id,)
    assert graph.backend.edges_between(v1, v2) == default.backend.edges_between(v1, v2)
    assert graph.backend.shortest_path(v1, v3) == default.backend.shortest_path(v1, v3)
    assert graph.backend.topological_sort() == default.backend.topological_sort()
    assert graph.edge_path(v1, v3) == default.edge_path(v1, v3)
