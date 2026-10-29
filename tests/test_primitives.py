from __future__ import annotations

import copy
import operator
import pickle
from typing import Any, cast

import pytest
import semver
from json_graph_lite.jgf import Graph as LiteGraph

from pyverge.schemas import (
    DataclassModelAdapter,
    JsonSchemaModelAdapter,
    ModelCodec,
    PydanticModelAdapter,
)
from pyverge.settings import VersioningSettings
from pyverge.versioning import (
    NO_DEFAULT,
    BackwardCompatibilityGuard,
    Canonicalizer,
    ChangeSet,
    Diff,
    DiffOrigin,
    EdgeKey,
    FieldChange,
    FieldDescriptor,
    FieldStatus,
    FrozenMap,
    JgfGraph,
    JgfNode,
    MigrationDescriptor,
    ModelRef,
    NodeId,
    TypeRef,
    VersionKey,
    VersionNode,
    default_canonicalizer,
    default_content_hasher,
    default_encoders,
)
from pyverge.versioning.errors import (
    BackwardCompatibilityError,
    MigrationApplicationError,
)
from tests.examples.dataclasses import PersonV1 as DataclassPersonV1
from tests.examples.json import (
    ADDRESS_V1_0_0,
    ADDRESS_V2_0_0,
    USER_V0_1_1_DEV_7,
    USER_V1_2_3,
    USER_V2_0_0,
    USER_V2_0_0_BETA_1,
    USER_V2025_01_01,
    USER_V2025_12_31,
    USER_V2026_02_28,
    USER_V2026_03_01,
)
from tests.examples.pydantic.chrono import (
    UserV20250101,
    UserV20251231,
    UserV20260228,
    UserV20260301_120530300Z,
)
from tests.examples.pydantic.semver import (
    UserV011Dev7,
    UserV1,
    UserV2,
    UserV3,
    UserV123,
    UserV200Beta1,
)
from tests.examples.pydantic.semver_nested import AddressV1, AddressV2
from tests.utils import edge_from_models, envelope_model

SHA256_HEX_LENGTH = 64


def _noop_migration(data: dict, context: Any = None) -> dict:
    return data


def _raise_migration(data: dict, context: Any = None) -> dict:
    raise RuntimeError("bad")


class TestOperations:
    @pytest.mark.parametrize(
        ("model_adapter", "left", "right", "op"),
        [
            (PydanticModelAdapter, UserV011Dev7, UserV123, "lt"),
            (JsonSchemaModelAdapter, USER_V0_1_1_DEV_7, USER_V1_2_3, "lt"),
            (PydanticModelAdapter, UserV200Beta1, UserV2, "lt"),
            (JsonSchemaModelAdapter, USER_V2_0_0_BETA_1, USER_V2_0_0, "lt"),
            (PydanticModelAdapter, UserV011Dev7, UserV011Dev7, "eq"),
            (JsonSchemaModelAdapter, USER_V0_1_1_DEV_7, USER_V0_1_1_DEV_7, "eq"),
            (PydanticModelAdapter, UserV20250101, UserV20251231, "lt"),
            (JsonSchemaModelAdapter, USER_V2025_01_01, USER_V2025_12_31, "lt"),
            (PydanticModelAdapter, UserV20250101, UserV20250101, "eq"),
            (JsonSchemaModelAdapter, USER_V2025_01_01, USER_V2025_01_01, "eq"),
        ],
        ids=[
            "dev-lt-pydantic",
            "dev-lt-json",
            "prerelease-lt-pydantic",
            "prerelease-lt-json",
            "dev-eq-pydantic",
            "dev-eq-json",
            "date-lt-pydantic",
            "date-lt-json",
            "date-eq-pydantic",
            "date-eq-json",
        ],
        indirect=["model_adapter"],
    )
    def test_version_operations(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left: Any,
        right: Any,
        op: str,
    ) -> None:
        comp = getattr(operator, op)
        assert comp(
            envelope_model(model_adapter, versioning_settings, left),
            envelope_model(model_adapter, versioning_settings, right),
        )

    @pytest.mark.parametrize(
        ("model_adapter", "left", "right", "op"),
        [
            (PydanticModelAdapter, UserV123, UserV20251231, "lt"),
            (JsonSchemaModelAdapter, USER_V1_2_3, USER_V2025_12_31, "lt"),
            (PydanticModelAdapter, UserV20250101, UserV123, "gt"),
            (JsonSchemaModelAdapter, USER_V2025_01_01, USER_V1_2_3, "gt"),
            (PydanticModelAdapter, UserV123, UserV20250101, "eq"),
            (JsonSchemaModelAdapter, USER_V1_2_3, USER_V2025_01_01, "eq"),
        ],
        ids=[
            "semver-lt-date-pydantic",
            "semver-lt-date-json",
            "date-gt-semver-pydantic",
            "date-gt-semver-json",
            "semver-eq-date-pydantic",
            "semver-eq-date-json",
        ],
        indirect=["model_adapter"],
    )
    def test_semver_vs_date(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left: Any,
        right: Any,
        op: str,
    ) -> None:
        with pytest.raises(TypeError):
            left_version = envelope_model(model_adapter, versioning_settings, left)
            right_version = envelope_model(model_adapter, versioning_settings, right)
            comp = getattr(operator, op)
            comp(left_version, right_version)

    @pytest.mark.parametrize(
        ("model_adapter", "models", "expected"),
        [
            (
                PydanticModelAdapter,
                [UserV200Beta1, UserV123, UserV011Dev7],
                [UserV011Dev7, UserV123, UserV200Beta1],
            ),
            (
                JsonSchemaModelAdapter,
                [USER_V2_0_0_BETA_1, USER_V1_2_3, USER_V0_1_1_DEV_7],
                [USER_V0_1_1_DEV_7, USER_V1_2_3, USER_V2_0_0_BETA_1],
            ),
            (
                PydanticModelAdapter,
                [UserV20260228, UserV20250101, UserV20260301_120530300Z],
                [UserV20250101, UserV20260228, UserV20260301_120530300Z],
            ),
            (
                JsonSchemaModelAdapter,
                [USER_V2026_02_28, USER_V2025_01_01, USER_V2026_03_01],
                [USER_V2025_01_01, USER_V2026_02_28, USER_V2026_03_01],
            ),
        ],
        ids=["semver-pydantic", "semver-json", "date-pydantic", "date-json"],
        indirect=["model_adapter"],
    )
    def test_sortable(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        models: list[Any],
        expected: list[Any],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        expected_versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in expected
        ]
        assert sorted(versions) == expected_versions

    @pytest.mark.parametrize(
        ("model_adapter", "left", "right", "op"),
        [
            (PydanticModelAdapter, AddressV1, UserV123, "lt"),
            (JsonSchemaModelAdapter, ADDRESS_V1_0_0, USER_V1_2_3, "lt"),
            (PydanticModelAdapter, AddressV1, AddressV2, "lt"),
            (JsonSchemaModelAdapter, ADDRESS_V1_0_0, ADDRESS_V2_0_0, "lt"),
            (PydanticModelAdapter, UserV123, AddressV1, "gt"),
            (JsonSchemaModelAdapter, USER_V1_2_3, ADDRESS_V1_0_0, "gt"),
            (PydanticModelAdapter, UserV011Dev7, UserV123, "lt"),
            (JsonSchemaModelAdapter, USER_V0_1_1_DEV_7, USER_V1_2_3, "lt"),
            (PydanticModelAdapter, UserV123, UserV123, "eq"),
            (JsonSchemaModelAdapter, USER_V1_2_3, USER_V1_2_3, "eq"),
            (PydanticModelAdapter, UserV20250101, UserV20260301_120530300Z, "lt"),
            (JsonSchemaModelAdapter, USER_V2025_01_01, USER_V2026_03_01, "lt"),
        ],
        ids=[
            "different_kind_lt-pydantic",
            "different_kind_lt-json",
            "same_kind_different_version_lt-pydantic",
            "same_kind_different_version_lt-json",
            "different_kind_gt-pydantic",
            "different_kind_gt-json",
            "same_kind_different_version_gt-pydantic",
            "same_kind_different_version_gt-json",
            "same_kind_same_version_eq-pydantic",
            "same_kind_same_version_eq-json",
            "same_kind_different_date_lt-pydantic",
            "same_kind_different_date_lt-json",
        ],
        indirect=["model_adapter"],
    )
    def test_different_kind(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left: Any,
        right: Any,
        op: str,
    ) -> None:
        left_version = envelope_model(model_adapter, versioning_settings, left)
        right_version = envelope_model(model_adapter, versioning_settings, right)
        comp = getattr(operator, op)
        assert comp(left_version, right_version)

    @pytest.mark.parametrize(
        ("model_adapter", "model"),
        [
            (PydanticModelAdapter, UserV123),
            (JsonSchemaModelAdapter, USER_V1_2_3),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_incompatible_type(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        subtests: pytest.Subtests,
        model: Any,
    ) -> None:
        """Comparing VersionedModel with an unrelated type raises NotImplementedError."""  # noqa: E501
        v = envelope_model(model_adapter, versioning_settings, model)
        for op, value in [
            ("lt", "not-a-version"),
            ("eq", None),
            ("gt", UserV20251231),
        ]:
            with subtests.test(op=op, value=value):
                with pytest.raises(NotImplementedError):
                    comp = getattr(operator, op)
                    comp(v, value)

    @pytest.mark.parametrize(
        ("model_adapter", "model1", "model2"),
        [
            (PydanticModelAdapter, UserV123, UserV2),
            (JsonSchemaModelAdapter, USER_V1_2_3, USER_V2_0_0),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_same_kind_different_version_hash(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        model1: Any,
        model2: Any,
    ) -> None:
        """Same kind, different versions produce distinct hashes."""
        v1 = envelope_model(model_adapter, versioning_settings, model1)
        v2 = envelope_model(model_adapter, versioning_settings, model2)
        assert hash(v1) != hash(v2)

    @pytest.mark.parametrize(
        ("model_adapter", "models", "expected"),
        [
            (PydanticModelAdapter, [UserV123, UserV011Dev7], 2),
            (JsonSchemaModelAdapter, [USER_V1_2_3, USER_V0_1_1_DEV_7], 2),
            (
                PydanticModelAdapter,
                [UserV20260228, UserV20250101, UserV20260301_120530300Z],
                3,
            ),
            (
                JsonSchemaModelAdapter,
                [USER_V2026_02_28, USER_V2025_01_01, USER_V2026_03_01],
                3,
            ),
        ],
        ids=["semver-pydantic", "semver-json", "date-pydantic", "date-json"],
        indirect=["model_adapter"],
    )
    def test_hashable(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        models: list[Any],
        expected: int,
    ) -> None:
        s = {envelope_model(model_adapter, versioning_settings, m) for m in models}
        assert len(s) == expected


class TestCanonicalization:
    def test_sorted_and_compact(self) -> None:
        assert (
            default_canonicalizer().dumps({"b": 1, "a": [2, 3]}) == '{"a":[2,3],"b":1}'
        )

    def test_deterministic_hash(self) -> None:
        left = default_content_hasher().digest({"a": 1, "b": [2, 3]})
        right = default_content_hasher().digest({"b": [2, 3], "a": 1})
        assert left == right
        assert len(left) == SHA256_HEX_LENGTH

    @pytest.mark.parametrize("value", [float("nan"), float("inf")])
    def test_rejects_non_finite_float(self, value: float) -> None:
        with pytest.raises(ValueError):
            default_canonicalizer().dumps({"value": value})

    def test_rejects_non_string_keys(self) -> None:
        with pytest.raises(TypeError):
            default_canonicalizer().dumps({1: "value"})

    def test_rejects_untyped_objects(self) -> None:
        with pytest.raises(TypeError):
            default_canonicalizer().dumps(object())

    def test_composes_a_custom_encoder(self) -> None:
        class Token:
            def __init__(self, value: str) -> None:
                self.value = value

        class TokenEncoder:
            def supports(self, value: object) -> bool:
                return isinstance(value, Token)

            def encode(self, value: Token, canonicalizer: Canonicalizer) -> str:
                return f"token:{value.value}"

        canonicalizer = Canonicalizer((TokenEncoder(), *default_encoders()))
        assert canonicalizer.dumps({"token": Token("abc")}) == '{"token":"token:abc"}'


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


class TestDiff:
    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter[semver.Version], UserV1, UserV2, _noop_migration]],
        indirect=True,
    )
    def test_from_pair_delegates_to_adapter(self, edge) -> None:
        source, target = edge.source, edge.target
        received: list[tuple[object, object]] = []

        class Adapter:
            def diff(self, source, target) -> Diff:
                received.append((source, target))
                return Diff(
                    source=source,
                    target=target,
                    fields=FrozenMap(),
                    origin=DiffOrigin.SCHEMA,
                )

        diff = Diff.from_pair(source, target, adapter=Adapter())

        assert received == [(source, target)]
        assert diff.source is source
        assert diff.target is target

    @pytest.mark.parametrize(
        ("adapter_cls", "source_model", "target_model", "expected"),
        [
            pytest.param(
                PydanticModelAdapter,
                UserV1,
                UserV20250101,
                "across strategies",
                id="strategy",
            ),
            pytest.param(
                PydanticModelAdapter,
                UserV1,
                AddressV1,
                "across kinds",
                id="kind",
            ),
        ],
    )
    def test_diff_rejects_invalid_pairs(
        self,
        versioning_settings,
        adapter_cls,
        source_model,
        target_model,
        expected: str,
    ) -> None:
        adapter = adapter_cls(codec=ModelCodec())
        source = envelope_model(adapter, versioning_settings, source_model)
        target = envelope_model(adapter, versioning_settings, target_model)
        with pytest.raises(ValueError, match=expected):
            Diff.from_pair(source, target, adapter=adapter)

    @pytest.mark.parametrize(
        ("edge", "added", "removed", "modified"),
        [
            pytest.param(
                [PydanticModelAdapter[semver.Version], UserV2, UserV3, _noop_migration],
                ["status"],
                [],
                ["age"],
                id="forward",
            ),
            pytest.param(
                [PydanticModelAdapter[semver.Version], UserV3, UserV2, _noop_migration],
                [],
                ["status"],
                ["age"],
                id="backward",
            ),
        ],
        indirect=["edge"],
    )
    def test_diff_field_usage(
        self,
        edge,
        added: list[str],
        removed: list[str],
        modified: list[str],
    ) -> None:
        diff = edge.diff
        assert diff.added_fields == added
        assert diff.removed_fields == removed
        assert sorted(diff.modified_fields) == modified
        assert diff.has_type_changes
        assert not diff.has_constraint_changes
        assert diff.modified_change("age", "type_changed") is not None
        assert diff.modified_change("age", "default_changed") is not None
        if "status" in added:
            assert diff.is_added("status")
            assert not diff.is_added_required("status")
            assert diff.added_default("status") == "active"
        else:
            assert diff.is_removed("status")
        assert diff.fingerprint_payload()["origin"] is DiffOrigin.SCHEMA

    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter[semver.Version], UserV2, UserV1, _noop_migration]],
        indirect=True,
    )
    def test_diff_predicates_inversion_and_change_set(self, edge) -> None:
        source, target = edge.source, edge.target
        diff = Diff(
            source=source,
            target=target,
            fields=FrozenMap(
                {
                    "added": FieldChange(
                        FieldStatus.ADDED,
                        {"required": True, "default": "x"},
                    ),
                    "removed": FieldChange(FieldStatus.REMOVED, {}),
                    "modified": FieldChange(
                        FieldStatus.MODIFIED,
                        {"required_changed": {"from": True, "to": False}},
                    ),
                    "expanded": FieldChange(
                        FieldStatus.MODIFIED,
                        {"required_changed": {"from": True, "to": False}},
                    ),
                    "contracted": FieldChange(
                        FieldStatus.MODIFIED,
                        {"required_changed": {"from": False, "to": True}},
                    ),
                    "same": FieldChange(FieldStatus.UNCHANGED, {}),
                }
            ),
            origin=DiffOrigin.SCHEMA,
        )

        assert diff.kind == "User"
        assert diff.edge == (source, target)
        assert diff.is_backward
        assert not diff.is_forward
        assert not diff.is_identity
        assert diff.has_additions
        assert diff.has_removals
        assert diff.has_modifications
        assert diff.unchanged_fields == ["same"]
        assert diff.added_field_info["added"]["required"]
        assert diff.added_default("added") == "x"
        assert diff.added_default("missing") is None
        assert diff.is_union_expansion("expanded")
        assert diff.is_union_contraction("contracted")
        assert diff.is_added("missing") is False
        assert diff.is_removed("missing") is False
        assert diff.is_modified("missing") is False
        assert diff.with_field("new", FieldChange(FieldStatus.ADDED, {})).is_added(
            "new"
        )
        assert diff.with_fields({"other": FieldChange(FieldStatus.ADDED, {})}).is_added(
            "other"
        )

        changes = diff.field_changes
        assert changes == ChangeSet(
            added=frozenset({"added"}),
            removed=frozenset({"removed"}),
            modified=frozenset({"modified", "expanded", "contracted"}),
        )
        assert changes.changed
        assert changes.summary("User") == [
            "User added: added",
            "User removed: removed",
            "User changed: contracted, expanded, modified",
        ]

        inverted = diff.inverted()
        assert inverted.is_added("removed")
        assert inverted.is_removed("added")
        assert inverted.is_backward

        guard = BackwardCompatibilityGuard(frozenset())
        report = guard.evaluate(diff)
        assert report.added_fields == ("added",)
        assert guard.required_additions(diff, report) == ("added",)

    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter[semver.Version], UserV1, UserV2, _noop_migration]],
        indirect=True,
    )
    def test_diff_render_and_materialize_delegate(self, edge) -> None:
        diff = edge.diff

        class Renderer:
            def render(self, diff: Any) -> str:
                return f"rendered:{diff.kind}"

        class Materializer:
            def materialize(self, diff: Any) -> str:
                return f"materialized:{diff.target.version}"

        assert diff.render(Renderer()) == "rendered:User"
        assert diff.materialize(Materializer()).startswith("materialized:")


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
        [[PydanticModelAdapter[semver.Version], UserV1]],
        indirect=True,
    )
    def test_node_repr(self, node) -> None:
        assert "VersionNode[Version]" in repr(node)

    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter[semver.Version], UserV1, UserV2, _noop_migration]],
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
        [[PydanticModelAdapter[semver.Version], UserV1, UserV2, _noop_migration]],
        indirect=True,
    )
    def test_version_edge_usage_and_failures(self, edge, versioning_settings) -> None:
        source, target = edge.source, edge.target
        adapter = PydanticModelAdapter(codec=ModelCodec())
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


class TestVersioningErrors:
    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter[semver.Version], UserV1, UserV2, _noop_migration]],
        indirect=True,
    )
    def test_migration_application_error_variants(self, edge) -> None:
        pair = MigrationApplicationError(("User", "1.0.0"))
        assert pair.source == "User"
        assert pair.target == "1.0.0"
        assert pair.kind == "unknown"
        assert "Migration failed: User → 1.0.0" in str(pair)

        with_reason = MigrationApplicationError(
            None, source=edge.source, target=edge.target, reason="boom"
        )
        assert with_reason.kind == "User"
        assert with_reason.reason == "boom"
        assert "boom" in str(with_reason)

        plain = MigrationApplicationError("User", reason="broken")
        assert str(plain) == "Migration failed for User: broken"

    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter[semver.Version], UserV1, UserV2, _noop_migration]],
        indirect=True,
    )
    def test_backward_compatibility_error(self, edge) -> None:
        error = BackwardCompatibilityError(
            "catalog",
            (edge.source, edge.target),
            removed=("legacy",),
            modified=("name",),
            required_additions=("email",),
        )

        assert error.key == (edge.source, edge.target)
        assert error.removed == ("legacy",)
        assert error.modified == ("name",)
        assert error.required_additions == ("email",)
        assert "structurally breaking" in str(error)
        assert "removed=['legacy']" in str(error)
        assert "modified=['name']" in str(error)
        assert "required_additions=['email']" in str(error)


class TestPrimitives:
    @pytest.mark.parametrize(
        "node",
        [[DataclassModelAdapter[semver.Version], DataclassPersonV1]],
        indirect=True,
    )
    def test_descriptor_projects_references_and_extends_immutably(self, node) -> None:
        descriptor = node.descriptor
        extended = descriptor.with_fields(
            FieldDescriptor(name="email", type_ref=TypeRef.primitive("string"))
        )

        assert set(descriptor.fields) == {"name", "address", "contacts"}
        assert descriptor.references
        assert set(extended.fields) == {"name", "address", "contacts", "email"}
        assert extended.without_fields("address").fields.keys() == {
            "name",
            "contacts",
            "email",
        }
        assert (
            extended.with_ref(
                ModelRef(provider="dataclass", model_id="demo.Other")
            ).ref.model_id
            == "demo.Other"
        )

    @pytest.mark.parametrize(
        "node",
        [[DataclassModelAdapter[semver.Version], DataclassPersonV1]],
        indirect=True,
    )
    def test_node_canonical_round_trip(self, node) -> None:
        payload = node.to_canonical()
        restored = VersionNode.from_canonical(payload, parse_version=ModelCodec().of)

        assert restored.to_canonical() == payload
        assert restored.descriptor == node.descriptor

    @pytest.mark.parametrize(
        "node",
        [[DataclassModelAdapter[semver.Version], DataclassPersonV1]],
        indirect=True,
    )
    def test_node_projects_extends_and_serializes(self, node) -> None:
        extended = node.with_fields(
            FieldDescriptor(name="email", type_ref=TypeRef.primitive("string"))
        )

        assert node.fields == frozenset({"name", "address", "contacts"})
        assert extended.fields == frozenset({"name", "address", "contacts", "email"})
        assert extended.without_fields("address").fields == frozenset(
            {"name", "contacts", "email"}
        )
        assert node.to_canonical()["model"] == node.descriptor.to_canonical()

        restored = pickle.loads(pickle.dumps(node))
        assert restored.to_canonical() == node.to_canonical()

        hasher = default_content_hasher()
        projected = JgfNode.from_addressable(node, hasher)
        assert projected.id == str(node)
        assert projected.metadata["content_hash"] == node.content_hash(hasher)
        assert projected.metadata["model"] == node.descriptor.to_canonical()
        assert node.model_id.endswith("PersonV1")


class TestFieldDefaults:
    def test_absent_default_is_omitted(self) -> None:
        field = FieldDescriptor(name="missing", type_ref=TypeRef.any())
        assert field.default is NO_DEFAULT
        assert "default" not in field.to_canonical()

    def test_explicit_none_default_is_kept(self) -> None:
        field = FieldDescriptor(name="explicit", type_ref=TypeRef.any(), default=None)
        assert field.to_canonical()["default"] is None

    def test_mapping_default_is_canonicalized(self) -> None:
        field = FieldDescriptor(
            name="mapping",
            type_ref=TypeRef.mapping(
                TypeRef.primitive("string"), TypeRef.primitive("integer")
            ),
            default={"b": 2, "a": 1},
        )
        assert field.to_canonical()["default"] == {"a": 1, "b": 2}


class TestJgfInterop:
    @pytest.mark.parametrize(
        ("model_adapter", "source", "target"),
        [
            (PydanticModelAdapter, UserV011Dev7, UserV123),
            (JsonSchemaModelAdapter, USER_V0_1_1_DEV_7, USER_V1_2_3),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_graph_loads_in_established_implementation(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source: Any,
        target: Any,
    ) -> None:
        source_node = envelope_model(model_adapter, versioning_settings, source)
        target_node = envelope_model(model_adapter, versioning_settings, target)
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            source,
            target,
            func=_noop_migration,
        )
        graph = JgfGraph.from_versions(
            [source_node, target_node],
            [edge],
            hasher=default_content_hasher(),
            id="pyverge-test",
            directed=True,
            metadata={"manifest_version": "v1"},
        )
        document = graph.to_dict()

        expected = {"graph": dict(document["graph"])}
        expected["graph"].pop("id")
        parsed = LiteGraph.from_dict(copy.deepcopy(document))

        # json-graph-lite does not preserve the graph-level id; it still
        # validates nodes/edges/metadata and round-trips them.
        assert parsed.directed is True
        assert {node.id for node in parsed.nodes} == {
            str(source_node),
            str(target_node),
        }
        assert {node.metadata["model"] for node in parsed.nodes} == {
            source_node.model_id,
            target_node.model_id,
        }
        assert parsed.edges[0].source == str(source_node)
        assert parsed.edges[0].target == str(target_node)
        assert parsed.edges[0].metadata["migration_id"] == edge.migration.identity
        assert parsed.to_dict() == expected
