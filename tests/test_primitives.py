from __future__ import annotations

import copy
import operator
import pickle
from dataclasses import replace
from typing import Any, cast

import pytest
import semver
from json_graph_lite.jgf import Graph as LiteGraph

from pyverge.providers import (
    JsonSchemaModelAdapter,
    PydanticModelAdapter,
)
from pyverge.settings import VersioningSettings
from pyverge.versioning import (
    NO_DEFAULT,
    Canonicalizer,
    Diff,
    FieldChange,
    FieldDescriptor,
    FieldStatus,
    FrozenMap,
    JgfGraph,
    JgfNode,
    MigrationIdentity,
    ModelDescriptor,
    ModelRef,
    TypeRef,
    VersionKey,
    VersionNode,
    default_canonicalizer,
    default_content_hasher,
    default_encoders,
)
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
    UserV2,
    UserV123,
    UserV200Beta1,
)
from tests.examples.pydantic.semver_nested import AddressV1, AddressV2
from tests.utils import edge_from_models, envelope_model

SHA256_HEX_LENGTH = 64


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
    def test_node_jgf_id(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        model: Any,
        expected: str,
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, model)
        assert node.jgf_id == expected
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
        assert edge.jgf_id == f"{edge.source.jgf_id}->{edge.target.jgf_id}"


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
        assert payload["id"] == node.jgf_id
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
        other = replace(
            edge, migration=MigrationIdentity("callable", "migration:other")
        )
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
        other = replace(
            edge,
            diff=replace(
                diff,
                fields={
                    **diff.fields,
                    "extra": FieldChange(FieldStatus.ADDED, {}),
                },
            ),
        )
        assert edge.content_hash(default_content_hasher()) != other.content_hash(
            default_content_hasher()
        )


class TestPrimitives:
    def _descriptor(self) -> ModelDescriptor:
        return ModelDescriptor(
            ref=ModelRef(provider="dataclass", model_id="demo.Person"),
            fields=FrozenMap(
                {
                    "name": FieldDescriptor(
                        name="name",
                        type_ref=TypeRef.primitive("string"),
                        references=(("Address", semver.Version.parse("1.0.0")),),
                    ),
                    "age": FieldDescriptor(
                        name="age",
                        default=None,
                        type_ref=TypeRef.primitive("integer"),
                    ),
                }
            ),
        )

    def test_type_refs_project_nested_types(self) -> None:
        union = TypeRef.union(TypeRef.primitive("string"), TypeRef.null())
        model = TypeRef.model(
            ModelRef(provider="pydantic", model_id="demo.Address"),
            version="1.0.0",
        )

        assert union.to_canonical() == {
            "kind": "union",
            "args": [{"kind": "string"}, {"kind": "null"}],
        }
        assert model.to_canonical() == {
            "kind": "model",
            "ref": {"model_id": "demo.Address", "provider": "pydantic"},
            "version": "1.0.0",
        }

    def test_field_default_projects_presence(self) -> None:
        missing = FieldDescriptor(name="missing", type_ref=TypeRef.any())
        explicit = FieldDescriptor(
            name="explicit", type_ref=TypeRef.any(), default=None
        )
        mapping = FieldDescriptor(
            name="mapping",
            type_ref=TypeRef.mapping(
                TypeRef.primitive("string"), TypeRef.primitive("integer")
            ),
            default={"b": 2, "a": 1},
        )

        assert missing.default is NO_DEFAULT
        assert "default" not in missing.to_canonical()
        assert explicit.to_canonical()["default"] is None
        assert mapping.to_canonical()["default"] == {"a": 1, "b": 2}

    def test_descriptor_derives_references_and_extends_immutably(self) -> None:
        descriptor = self._descriptor()
        extended = descriptor.with_fields(
            FieldDescriptor(
                name="address",
                type_ref=TypeRef.any(),
                references=(("Address", semver.Version.parse("2.0.0")),),
            )
        )

        assert descriptor.references == frozenset(
            {("Address", semver.Version.parse("1.0.0"))}
        )
        assert extended.references == frozenset(
            {
                ("Address", semver.Version.parse("1.0.0")),
                ("Address", semver.Version.parse("2.0.0")),
            }
        )
        assert descriptor.fields.keys() == {"name", "age"}
        assert extended.fields.keys() == {"name", "age", "address"}
        assert extended.without_fields("age").fields.keys() == {
            "name",
            "address",
        }
        assert (
            extended.with_ref(
                ModelRef(provider="dataclass", model_id="demo.Other")
            ).ref.model_id
            == "demo.Other"
        )

    def test_node_projects_and_extends_descriptor(self) -> None:
        descriptor = self._descriptor()
        node = VersionNode[semver.Version](
            key=VersionKey[semver.Version](
                _value=semver.Version.parse("2.0.0"),
                _kind="Person",
            ),
            descriptor=descriptor,
        )
        extended = node.with_fields(
            FieldDescriptor(name="email", type_ref=TypeRef.any())
        )

        assert node.model_id == "demo.Person"
        assert node.fields == frozenset({"name", "age"})
        assert extended.fields == frozenset({"name", "age", "email"})
        assert extended.without_fields("age").fields == frozenset({"name", "email"})
        assert node.to_canonical() == {
            "id": "Person@2.0.0",
            "kind": "Person",
            "version": "2.0.0",
            "model": descriptor.to_canonical(),
        }

        restored = pickle.loads(pickle.dumps(node))
        assert restored.to_canonical() == node.to_canonical()

        hasher = default_content_hasher()
        projected = JgfNode.from_addressable(node, hasher)
        assert projected.id == node.jgf_id
        assert projected.metadata["content_hash"] == node.content_hash(hasher)
        assert projected.metadata["model"] == descriptor.to_canonical()
        with pytest.raises(ValueError, match="no runtime model handle"):
            _ = node.model


def _noop_migration(data: dict, context: Any = None) -> dict:
    return data


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
            source_node.jgf_id,
            target_node.jgf_id,
        }
        assert {node.metadata["model"] for node in parsed.nodes} == {
            source_node.model_id,
            target_node.model_id,
        }
        assert parsed.edges[0].source == source_node.jgf_id
        assert parsed.edges[0].target == target_node.jgf_id
        assert parsed.edges[0].metadata["migration_id"] == edge.migration.identity
        assert parsed.to_dict() == expected
