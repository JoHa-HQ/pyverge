from __future__ import annotations

import copy
import pickle
from dataclasses import FrozenInstanceError
from typing import Any, cast

import pendulum
import pytest
import semver

from pyverge.schemas import (
    JsonSchemaModelAdapter,
    ModelCodec,
    PydanticModelAdapter,
)
from pyverge.settings import VersioningSettings
from pyverge.versioning import (
    Diff,
    EdgeKey,
    FieldChange,
    FieldStatus,
    FrozenMap,
    MigrationDescriptor,
    NodeId,
    VersionKey,
    default_content_hasher,
)
from pyverge.versioning.errors import (
    MigrationApplicationError,
)
from tests.examples.json import (
    USER_V0_1_1_DEV_7,
    USER_V1_2_3,
)
from tests.examples.pydantic.semver import (
    UserV011Dev7,
    UserV1,
    UserV2,
    UserV123,
)
from tests.utils import edge_from_models, envelope_model

SHA256_HEX_LENGTH = 64


def _noop_migration(data: dict, context: Any = None) -> dict:
    return data


def _raise_migration(data: dict, context: Any = None) -> dict:
    raise RuntimeError("bad")


class TestGraphIdentity:
    @pytest.mark.parametrize(
        ("model_adapter", "model", "expected"),
        [
            (PydanticModelAdapter, UserV123, "User@1.2.3"),
            (JsonSchemaModelAdapter, USER_V1_2_3, "User@1.2.3"),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_node_identity(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        model: Any,
        expected: str,
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, model)
        assert isinstance(node.id, NodeId)
        assert str(node.id) == expected
        assert str(node) == expected

    @pytest.mark.parametrize(
        ("model_adapter", "source", "target"),
        [
            (PydanticModelAdapter, UserV011Dev7, UserV123),
            (JsonSchemaModelAdapter, USER_V0_1_1_DEV_7, USER_V1_2_3),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_edge_jgf_id(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source: Any,
        target: Any,
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            source,
            target,
            func=_noop_migration,
        )
        assert str(edge.id) == f"{edge.source}->{edge.target}"


class TestContentAddress:
    @pytest.mark.parametrize(
        ("model_adapter", "model"),
        [
            (PydanticModelAdapter, UserV123),
            (JsonSchemaModelAdapter, USER_V1_2_3),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_node_content_hash(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        model: Any,
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, model)
        payload = node.content_payload()
        assert payload["id"] == str(node.id)
        assert payload["model"] == node.model_id
        assert node.content_hash(
            default_content_hasher()
        ) == default_content_hasher().digest(payload)

    @pytest.mark.parametrize(
        ("model_adapter", "source", "target"),
        [
            (PydanticModelAdapter, UserV011Dev7, UserV123),
            (JsonSchemaModelAdapter, USER_V0_1_1_DEV_7, USER_V1_2_3),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_edge_content_hash_is_deterministic(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source: Any,
        target: Any,
    ) -> None:
        left = edge_from_models(
            model_adapter,
            versioning_settings,
            source,
            target,
            func=_noop_migration,
        )
        right = edge_from_models(
            model_adapter,
            versioning_settings,
            source,
            target,
            func=_noop_migration,
        )
        assert left.migration.identity == right.migration.identity
        assert left.content_hash(default_content_hasher()) == right.content_hash(
            default_content_hasher()
        )

    @pytest.mark.parametrize(
        ("model_adapter", "source", "target"),
        [
            (PydanticModelAdapter, UserV011Dev7, UserV123),
            (JsonSchemaModelAdapter, USER_V0_1_1_DEV_7, USER_V1_2_3),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_migration_identity_changes_hash(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source: Any,
        target: Any,
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            source,
            target,
            func=_noop_migration,
        )
        other = edge.with_migration(MigrationDescriptor("callable", "migration:other"))
        assert edge.content_hash(default_content_hasher()) != other.content_hash(
            default_content_hasher()
        )

    @pytest.mark.parametrize(
        ("model_adapter", "source", "target"),
        [
            (PydanticModelAdapter, UserV011Dev7, UserV123),
            (JsonSchemaModelAdapter, USER_V0_1_1_DEV_7, USER_V1_2_3),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_diff_fingerprint_changes_hash(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source: Any,
        target: Any,
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            source,
            target,
            func=_noop_migration,
        )
        diff = cast(Diff, edge.diff)
        other = edge.with_diff(
            diff.with_field(
                "extra",
                FieldChange(FieldStatus.ADDED, {}),
            )
        )
        assert edge.content_hash(default_content_hasher()) != other.content_hash(
            default_content_hasher()
        )


class TestNodeIdentity:
    def test_node_id_parses_and_orders(self) -> None:
        first = NodeId("orders", "Order", semver.Version.parse("1.2.3"))
        second = NodeId("orders", "Order", semver.Version.parse("1.10.0"))

        assert first.version == semver.Version.parse("1.2.3")
        assert first < second
        assert hash(first) == hash(
            NodeId("orders", "Order", semver.Version.parse("1.2.3"))
        )
        assert first != NodeId("other", "Order", semver.Version.parse("1.2.3"))
        assert str(first) == "orders:Order@1.2.3"

    def test_node_id_rejects_invalid_version(self) -> None:
        with pytest.raises(ValueError):
            NodeId.from_string("orders", "Order", "not-a-version")

    def test_version_key_ref_is_not_identity(self) -> None:
        left = VersionKey(
            namespace="orders", kind="Order", version=semver.Version.parse("1.0.0")
        )
        right = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
            ref=object(),
        )

        assert left == right
        assert hash(left) == hash(right)

    def test_edge_key_rejects_cross_namespace(self) -> None:
        with pytest.raises(ValueError, match="Cross-namespace"):
            EdgeKey(
                source=NodeId[semver.Version](
                    "a", "Order", semver.Version.parse("1.0.0")
                ),
                target=NodeId[semver.Version](
                    "b", "Order", semver.Version.parse("2.0.0")
                ),
            )

    def test_key_digests_exclude_metadata_ref(self) -> None:
        hasher = default_content_hasher()
        node_a = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
            ref=object(),
        )
        node_b = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
            ref=object(),
        )
        assert node_a.digest(hasher) == node_b.digest(hasher)

        edge_a = EdgeKey(
            source=NodeId[semver.Version](
                "orders", "Order", semver.Version.parse("1.0.0")
            ),
            target=NodeId[semver.Version](
                "orders", "Order", semver.Version.parse("2.0.0")
            ),
            ref=object(),
        )
        edge_b = EdgeKey(
            source=NodeId[semver.Version](
                "orders", "Order", semver.Version.parse("1.0.0")
            ),
            target=NodeId[semver.Version](
                "orders", "Order", semver.Version.parse("2.0.0")
            ),
            ref=object(),
        )
        assert edge_a.digest(hasher) == edge_b.digest(hasher)

    def test_node_id_parse_semver_and_date(self) -> None:
        semver_node = NodeId.parse("orders", "Order", "1.2.3")
        date_node = NodeId.parse("orders", "Order", "2026-10-30")

        assert semver_node.version == semver.Version.parse("1.2.3")
        assert date_node.version == pendulum.Date(2026, 10, 30)
        assert NodeId.parse("orders", "Order", semver_node.version) == semver_node

    def test_node_id_is_frozen_and_slotted(self) -> None:
        node = NodeId.parse("orders", "Order", "1.2.3")

        with pytest.raises(FrozenInstanceError):
            node.kind = "Other"  # ty: ignore[invalid-assignment]
        assert not hasattr(node, "__dict__")
        assert not hasattr(node, "jgf_id")

    @pytest.mark.parametrize(
        ("namespace", "kind", "version", "equal"),
        [
            pytest.param("billing", "Order", "1.0.0", False, id="namespace"),
            pytest.param("orders", "Invoice", "1.0.0", False, id="kind"),
            pytest.param("orders", "Order", "2.0.0", False, id="version"),
            pytest.param("orders", "Order", "1.0.0", True, id="same"),
        ],
    )
    def test_node_id_distinguishes_namespace_kind_and_version(
        self,
        namespace: str,
        kind: str,
        version: str,
        equal: bool,
    ) -> None:
        base = NodeId.parse("orders", "Order", "1.0.0")
        other = NodeId.parse(namespace, kind, version)

        assert (base == other) is equal

    def test_version_key_ref_survives_copy_and_pickle(self) -> None:
        key = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
            ref=object(),
        )

        copied = copy.copy(key)
        restored = pickle.loads(pickle.dumps(key))

        assert copied.ref is key.ref
        assert restored.ref is not None
        assert restored == key
        assert hash(restored) == hash(key)

    def test_edge_key_rejects_cross_kind(self) -> None:
        with pytest.raises(ValueError, match="Cross-kind"):
            EdgeKey(
                source=NodeId.parse("orders", "Order", "1.0.0"),
                target=NodeId.parse("orders", "Invoice", "2.0.0"),
            )

    def test_key_digest_includes_namespace(self) -> None:
        hasher = default_content_hasher()
        left = VersionKey(
            namespace="orders",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
        )
        right = VersionKey(
            namespace="billing",
            kind="Order",
            version=semver.Version.parse("1.0.0"),
        )

        assert left.digest(hasher) != right.digest(hasher)

    def test_identity_objects_have_no_legacy_names(self) -> None:
        key = VersionKey.parse("orders", "Order", "1.0.0")
        edge = EdgeKey.from_pair(
            NodeId.parse("orders", "Order", "1.0.0"),
            NodeId.parse("orders", "Order", "2.0.0"),
        )

        for value in (key, edge):
            assert not hasattr(value, "_value")
            assert not hasattr(value, "_kind")
            assert not hasattr(value, "jgf_id")

    def test_jgf_ids_are_namespace_prefixed(self) -> None:
        node = NodeId[semver.Version](
            "com.joha.order", "Order", semver.Version.parse("1.0.0")
        )
        assert str(node) == "com.joha.order:Order@1.0.0"


class TestGraphPrimitives:
    def test_version_key_identity_and_repr(self) -> None:
        key = VersionKey[semver.Version](
            namespace="test",
            kind="User",
            version=semver.Version.parse("1.2.3"),
            ref=object(),
        )

        assert str(key) == "test:User@1.2.3"
        assert hash(key) == hash(
            VersionKey[semver.Version](
                namespace="test",
                kind="User",
                version=semver.Version.parse("1.2.3"),
            )
        )
        assert "VersionKey[Version]" in repr(key)

    @pytest.mark.parametrize(
        "node",
        [[PydanticModelAdapter, UserV1]],
        indirect=True,
    )
    def test_node_repr(self, node) -> None:
        assert "VersionNode[Version]" in repr(node)

    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter, UserV1, UserV2, _noop_migration]],
        indirect=True,
    )
    def test_edge_key_identity_and_comparison(self, edge) -> None:
        source, target = edge.source, edge.target
        edge_key = EdgeKey.from_pair(source, target)
        same = EdgeKey.from_version_edge(edge)

        assert edge_key.kind == "User"
        assert edge_key.key == (source, target)
        assert edge_key.key == (source, target)
        assert edge_key == same
        assert hash(edge_key) == hash(same)
        assert str(edge_key) == "User@1.0.0->User@2.0.0"
        assert edge_key < EdgeKey.from_pair(target, source)
        with pytest.raises(NotImplementedError):
            edge_key == "other"
        with pytest.raises(NotImplementedError):
            edge_key < "other"

    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter, UserV1, UserV2, _noop_migration]],
        indirect=True,
    )
    def test_version_edge_usage_and_failures(self, edge, versioning_settings) -> None:
        source, target = edge.source, edge.target
        adapter = PydanticModelAdapter(
            codec=ModelCodec(
                namespace="", version_property="version", kind_property="kind"
            )
        )
        other = edge_from_models(
            adapter,
            versioning_settings,
            UserV2,
            UserV1,
            func=_noop_migration,
        )
        failing = edge_from_models(
            adapter,
            versioning_settings,
            UserV1,
            UserV2,
            func=_raise_migration,
        )

        assert edge.kind == "User"
        assert edge.key == (source, target)
        assert edge.key == (source, target)
        assert str(edge) == "User@1.0.0->User@2.0.0"
        assert edge.content_payload(default_content_hasher())["id"] == str(edge)
        assert len(edge.content_hash(default_content_hasher())) == SHA256_HEX_LENGTH
        assert edge.to_jgf().source == str(source)
        assert edge < other
        assert other > edge
        assert edge != other
        assert edge < EdgeKey.from_pair(target, source)
        assert edge == EdgeKey.from_pair(source, target)
        for operation in (
            lambda: edge < "other",
            lambda: edge > "other",
            lambda: edge == "other",
        ):
            with pytest.raises(NotImplementedError):
                operation()

        with pytest.raises(MigrationApplicationError, match="bad"):
            failing({})

    def test_frozen_map_hash_repr_and_dict(self) -> None:
        frozen = FrozenMap({"b": 2, "a": 1})
        assert hash(frozen) == hash(FrozenMap({"a": 1, "b": 2}))
        assert repr(frozen) == "FrozenMap({'b': 2, 'a': 1})"
        assert frozen.to_dict() == {"b": 2, "a": 1}
