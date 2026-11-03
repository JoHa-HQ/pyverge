# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Any, cast

import pytest
import semver

from pyverge.core.versioning import (
    EdgeKey,
    EdgeRef,
    FrozenMap,
    HookRef,
    KeyRef,
    MigrationDescriptor,
    MigrationRef,
    ModelDescriptor,
    ModelRef,
    NodeId,
    NodeRef,
    VersionEdge,
    VersionKey,
    VersionNode,
    default_content_hasher,
    parse_version,
)
from pyverge.core.versioning.identity.metadata import ModelRef as MetadataModelRef


def _model_ref(*, metadata: dict[str, object] | None = None) -> ModelRef:
    return ModelRef(
        provider_id="test",
        entity_id="tests.User",
        metadata=metadata or {},
    )


def _node(ref: ModelRef) -> VersionNode[semver.Version]:
    return VersionNode[semver.Version](
        namespace="test",
        kind="User",
        version=semver.Version.parse("1.0.0"),
        ref=ref,
        descriptor=ModelDescriptor(ref=ref, fields=FrozenMap()),
    )


def test_model_ref_has_one_definition() -> None:
    assert ModelRef is MetadataModelRef


def test_ref_hierarchy() -> None:
    assert isinstance(NodeRef(), KeyRef)
    assert isinstance(EdgeRef(), KeyRef)
    assert isinstance(_model_ref(), NodeRef)
    assert isinstance(MigrationRef(provider_id="callable", entity_id="m1"), EdgeRef)
    assert isinstance(
        HookRef(provider_id="test", entity_id="h1", config={"mode": "audit"}),
        EdgeRef,
    )


def test_key_ref_metadata_and_digest() -> None:
    hasher = default_content_hasher()
    ref = KeyRef(metadata={"source": "app.models"})

    assert ref.get("source") == "app.models"
    assert ref.get("missing", "fallback") == "fallback"
    assert ref.merged(extra=True).metadata == {
        "source": "app.models",
        "extra": True,
    }
    assert ref.digest(hasher) != KeyRef().digest(hasher)
    assert KeyRef.from_canonical(ref.to_canonical()) == ref


def test_model_ref_canonical_and_identity() -> None:
    left = _model_ref(metadata={"module": "app.models"})
    right = _model_ref(metadata={"module": "other"})

    # Metadata is content, not provider identity.
    assert left == right
    assert hash(left) == hash(right)
    assert left.to_canonical()["metadata"] == {"module": "app.models"}

    restored = ModelRef.from_canonical(left.to_canonical())
    assert restored == left
    assert restored.metadata == {"module": "app.models"}


def test_migration_ref_canonical() -> None:
    ref = MigrationRef(
        provider_id="callable",
        entity_id="user_v1_to_v2",
        metadata={"format": "python"},
    )

    assert ref.to_canonical() == {
        "provider_id": "callable",
        "entity_id": "user_v1_to_v2",
        "metadata": {"format": "python"},
    }
    assert MigrationRef.from_canonical(ref.to_canonical()) == ref


def test_hook_ref_canonical() -> None:
    ref = HookRef(provider_id="callable", entity_id="audit", config={"mode": "async"})

    restored = HookRef.from_canonical(ref.to_canonical())
    assert restored == ref
    assert restored.config == {"mode": "async"}


def test_version_key_requires_ref() -> None:
    with pytest.raises(TypeError):
        cast("Any", VersionKey)(
            namespace="test",
            kind="User",
            version=semver.Version.parse("1.0.0"),
        )


def test_version_key_parse_supplies_default_ref() -> None:
    key = VersionKey.parse("test", "User", "1.0.0")

    assert isinstance(key.ref, NodeRef)
    assert key.ref.metadata == {}


def test_key_only_can_carry_model_ref() -> None:
    ref = _model_ref(metadata={"source": "lock"})
    key = VersionKey.parse("test", "User", "1.0.0", ref=ref)

    assert key.ref is ref
    assert key.ref.get("source") == "lock"


def test_edge_key_requires_or_defaults_ref() -> None:
    source = NodeId.parse("test", "User", "1.0.0")
    target = NodeId.parse("test", "User", "2.0.0")

    with pytest.raises(TypeError):
        cast("Any", EdgeKey)(source=source, target=target)

    key = EdgeKey.from_pair(source, target)
    assert isinstance(key.ref, EdgeRef)


def test_edge_key_inherits_version_edge_ref() -> None:
    ref = MigrationRef(provider_id="callable", entity_id="m1")
    edge = VersionEdge(
        source=_node(_model_ref()),
        target=_node(_model_ref()),
        ref=ref,
        diff=cast("Any", object()),
        func=lambda data, context=None: data,
        migration=MigrationDescriptor("callable", "m1"),
    )

    assert EdgeKey.from_version_edge(edge).ref == ref


def test_version_node_requires_model_ref() -> None:
    with pytest.raises(TypeError):
        VersionNode[semver.Version](
            namespace="test",
            kind="User",
            version=semver.Version.parse("1.0.0"),
            ref=NodeRef(),
            descriptor=ModelDescriptor(
                ref=_model_ref(),
                fields=FrozenMap(),
            ),
        )


def test_version_node_canonical_round_trip() -> None:
    node = _node(_model_ref(metadata={"module": "app.models"}))
    payload = node.to_canonical()

    assert payload["ref"] == node.ref.to_canonical()
    restored = VersionNode.from_canonical(payload, parse_version=parse_version)
    assert restored.to_canonical() == payload


def test_version_edge_requires_migration_ref() -> None:
    source = _node(_model_ref())
    target = _node(_model_ref())

    with pytest.raises(TypeError):
        VersionEdge(
            source=source,
            target=target,
            ref=cast("Any", NodeRef()),
            diff=cast("Any", object()),
            func=lambda data, context=None: data,
            migration=MigrationDescriptor("callable", "m1"),
        )
