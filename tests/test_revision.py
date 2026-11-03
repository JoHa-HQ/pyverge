# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pendulum
import pytest
import semver

from pyverge.core.graph import RevisionMismatchError
from pyverge.core.versioning import HookRef, NodeRef, VersionKey
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.chrono import UserV20250310, UserV20251231
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
)

SEMVER_REGISTRY = [
    semver.Version,
    "test",
    [UserV1, UserV2],
    [((UserV1, UserV2), migrate_v1_to_v2)],
]
DATE_REGISTRY = [
    pendulum.Date,
    "test",
    [UserV20250310, UserV20251231],
    [],
]


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, SEMVER_REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_snapshot_revision_is_stable(engine) -> None:
    first = engine.snapshot()
    second = engine.snapshot()

    assert first.revision == second.revision
    assert first.revision.version_strategy == "semver"
    assert first.revision.versions == {"User": ("1.0.0", "2.0.0")}
    assert first.content_digest() == second.content_digest()
    assert first.manifest_digest() == second.manifest_digest()
    assert first.same_content(second)
    assert first.same_manifest(second)


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, SEMVER_REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_snapshot_revision_changes_with_content(engine) -> None:
    before = engine.snapshot()

    engine.store_model(UserV3)
    after = engine.snapshot()

    assert before.revision.versions == {"User": ("1.0.0", "2.0.0")}
    assert after.revision.versions == {"User": ("1.0.0", "2.0.0", "3.0.0")}
    assert not before.same_content(after)
    assert not before.same_manifest(after)


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, SEMVER_REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_snapshot_revision_changes_when_hook_added(engine) -> None:
    before = engine.snapshot()
    edge = engine.registry.migrations("User")[0]

    engine.add_hook(
        edge,
        HookRef(provider_id="test", entity_id="audit", config={}),
    )
    after = engine.snapshot()

    assert not before.same_content(after)
    assert not before.same_manifest(after)


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, [semver.Version, "test", [], []]]],
    indirect=["model_adapter", "registry"],
)
def test_hydration_changes_content_not_version_vector(engine) -> None:
    engine.registry.store(
        VersionKey(
            namespace="test",
            kind="User",
            version=semver.Version.parse("1.0.0"),
            ref=NodeRef(),
        )
    )
    before = engine.snapshot()

    engine.registry.hydrate(engine.adapter.versionable(UserV1))
    after = engine.snapshot()

    assert before.revision.versions == after.revision.versions
    assert before.content_digest() != after.content_digest()
    assert not before.same_content(after)


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, SEMVER_REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_snapshot_accepts_current_revision_and_rejects_stale(engine) -> None:
    graph = engine.snapshot()

    assert engine.snapshot(revision=graph.revision).revision == graph.revision

    engine.store_model(UserV3)
    with pytest.raises(RevisionMismatchError):
        engine.snapshot(revision=graph.revision)


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, [semver.Version, "test", [], []]]],
    indirect=["model_adapter", "registry"],
)
def test_empty_graph_has_no_version_strategy(engine) -> None:
    revision = engine.snapshot().revision

    assert revision.version_strategy == "none"
    assert revision.versions == {}


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, DATE_REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_date_graph_uses_date_strategy(engine) -> None:
    revision = engine.snapshot().revision

    assert revision.version_strategy == "date"
    assert revision.versions == {
        "User": ("2025-03-10", "2025-12-31"),
    }


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, [semver.Version, "test", [], []]]],
    indirect=["model_adapter", "registry"],
)
def test_mixed_version_strategies_are_rejected(engine) -> None:
    engine.registry.store(
        VersionKey(
            namespace="test",
            kind="User",
            version=semver.Version.parse("1.0.0"),
            ref=NodeRef(),
        )
    )

    with pytest.raises(TypeError, match="Cannot compare"):
        engine.registry.store(
            VersionKey(
                namespace="test",
                kind="Invoice",
                version=pendulum.date(2026, 1, 1),
                ref=NodeRef(),
            )
        )


@dataclass(frozen=True)
class BuildNumber:
    value: int

    def __str__(self) -> str:
        return f"build-{self.value}"

    def __lt__(self, other: Any) -> bool:
        return self.value < other.value

    def __gt__(self, other: Any) -> bool:
        return self.value > other.value

    def __le__(self, other: Any) -> bool:
        return self.value <= other.value

    def __ge__(self, other: Any) -> bool:
        return self.value >= other.value

    def __hash__(self) -> int:
        return hash(self.value)


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, [semver.Version, "test", [], []]]],
    indirect=["model_adapter", "registry"],
)
def test_custom_version_value_participates_in_revision(engine) -> None:
    for value in (2, 1):
        engine.registry.store(
            VersionKey(
                namespace="test",
                kind="Pipeline",
                version=BuildNumber(value),
                ref=NodeRef(),
            )
        )

    revision = engine.snapshot().revision

    assert revision.versions == {"Pipeline": ("build-1", "build-2")}
    assert revision.version_strategy.endswith("BuildNumber")
