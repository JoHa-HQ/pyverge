# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
from typing import Any

import pytest
from json_graph_lite.jgf import Graph as LiteGraph

from pyverge.cli.jgf import JgfGraph
from pyverge.core.registry import CompatibilityReport
from pyverge.core.versioning import (
    Canonicalizer,
    ChangeSet,
    Diff,
    DiffOrigin,
    FieldChange,
    FieldDescriptor,
    FieldStatus,
    FrozenMap,
    ModelRef,
    TypeRef,
    VersionNode,
    default_canonicalizer,
    default_content_hasher,
    default_encoders,
    parse_version,
)
from pyverge.core.versioning.errors import (
    MigrationApplicationError,
)
from pyverge.schemas import (
    DataclassModelAdapter,
    JsonSchemaModelAdapter,
    ModelCodec,
    PydanticModelAdapter,
)
from pyverge.settings import VersioningSettings
from tests.examples.dataclasses import PersonV1 as DataclassPersonV1
from tests.examples.json import (
    USER_V0_1_1_DEV_7,
    USER_V1_2_3,
)
from tests.examples.pydantic.chrono import (
    UserV20250101,
)
from tests.examples.pydantic.semver import (
    UserV011Dev7,
    UserV1,
    UserV2,
    UserV123,
)
from tests.examples.pydantic.semver_nested import AddressV1
from tests.utils import edge_from_models, envelope_model

SHA256_HEX_LENGTH = 64


def _noop_migration(data: dict, context: Any = None) -> dict:
    return data


def _raise_migration(data: dict, context: Any = None) -> dict:
    raise RuntimeError("bad")


class TestCanonicalization:
    def test_sorted_and_compact(self) -> None:
        assert (
            default_canonicalizer().dumps({"b": 1, "a": [2, 3]}) == '{"a":[2,3],"b":1}'
        )

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


class TestDiff:
    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter, UserV1, UserV2, _noop_migration]],
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
        adapter = adapter_cls(
            codec=ModelCodec(
                namespace="test", version_property="version", kind_property="kind"
            )
        )
        source = envelope_model(adapter, versioning_settings, source_model)
        target = envelope_model(adapter, versioning_settings, target_model)
        with pytest.raises(ValueError, match=expected):
            Diff.from_pair(source, target, adapter=adapter)

    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter, UserV2, UserV1, _noop_migration]],
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

        report = CompatibilityReport.from_diff(diff, identity_fields=frozenset())
        assert report.added_fields == ("added",)
        assert report.required_additions(diff) == ("added",)


class TestVersioningErrors:
    @pytest.mark.parametrize(
        "edge",
        [[PydanticModelAdapter, UserV1, UserV2, _noop_migration]],
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


class TestPrimitives:
    @pytest.mark.parametrize(
        "node",
        [[DataclassModelAdapter, DataclassPersonV1]],
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
                ModelRef(provider_id="dataclass", entity_id="demo.Other")
            ).ref.entity_id
            == "demo.Other"
        )

    @pytest.mark.parametrize(
        "node",
        [[DataclassModelAdapter, DataclassPersonV1]],
        indirect=True,
    )
    def test_node_canonical_round_trip(self, node) -> None:
        payload = node.to_canonical()
        restored = VersionNode.from_canonical(payload, parse_version=parse_version)

        assert restored.to_canonical() == payload
        assert restored.descriptor == node.descriptor


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
