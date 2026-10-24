"""Export domain: JGF projection, manifest spec, and injected hashing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pendulum
import pytest
import semver

from pyverge import types
from pyverge.export import (
    ManifestDiff,
    ManifestExporter,
    ManifestSpec,
    ManifestVersion,
)
from pyverge.jgf import JgfExporter
from pyverge.migration import JsonSchemaModelAdapter, PydanticModelAdapter, Registry
from pyverge.providers.types import ModelHandle
from pyverge.versioning import (
    ChangeSet,
    ContentHasher,
    Diff,
    DiffOrigin,
    FieldChange,
    FieldStatus,
    default_canonicalizer,
)
from tests.examples.json import USER_V2025_01_01, USER_V2025_03_10
from tests.examples.pydantic.semver import UserV1, UserV2


class _FixedAlgorithm:
    @property
    def name(self) -> str:
        return "fixed"

    def digest(self, data: bytes) -> str:
        return "fixed-hash"


@pytest.mark.parametrize(
    "model_adapter, registry, models",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "export_semver", [UserV1, UserV2], []],
            [UserV1, UserV2],
            id="semver",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            [
                pendulum.Date,
                "export_json_chrono",
                [USER_V2025_01_01, USER_V2025_03_10],
                [],
            ],
            [USER_V2025_01_01, USER_V2025_03_10],
            id="json_chrono",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_manifest_uses_explicit_spec_and_injected_hasher(
    registry: Registry[types.VersionValue],
    models: list[ModelHandle],
    snapshot,
) -> None:
    hasher = ContentHasher(default_canonicalizer(), _FixedAlgorithm())
    exporter = JgfExporter(hasher)
    spec = ManifestSpec(
        graph_id="custom-id",
        label="custom label",
        manifest_version=ManifestVersion.V1,
        tool_version="0.0-test",
    )

    generated_at = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    document = ManifestExporter(spec, exporter).export(
        registry, manager="tests", generated_at=generated_at
    )
    assert document == snapshot
    assert exporter.content_hash(registry) == "fixed-hash"


def test_change_set_summary_and_flag() -> None:
    changes = ChangeSet(added=frozenset({"b", "a"}))

    assert changes.changed is True
    assert changes.summary("node") == ["node added: a, b"]


def test_manifest_diff_uses_change_sets() -> None:
    left = {"graph": {"nodes": {"User@1.0.0": {}}, "edges": []}}
    right = {"graph": {"nodes": {"User@1.0.0": {}, "User@2.0.0": {}}, "edges": []}}

    diff = ManifestDiff.compare(left, right)

    assert diff.changed is True
    assert diff.nodes.added == frozenset({"User@2.0.0"})
    assert diff.nodes.removed == frozenset()
    assert "node added: User@2.0.0" in diff.summary()


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "diff_semver", [UserV1, UserV2], []],
            id="semver_diff",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_diff_exposes_field_changes(
    registry: Registry[types.VersionValue],
) -> None:
    diff = Diff(
        source=registry.versions[0],
        target=registry.versions[1],
        fields={
            "age": FieldChange(FieldStatus.ADDED, {}),
            "legacy": FieldChange(FieldStatus.REMOVED, {}),
            "name": FieldChange(FieldStatus.MODIFIED, {"type_changed": True}),
        },
        origin=DiffOrigin.SCHEMA,
    )

    assert diff.field_changes == ChangeSet(
        added=frozenset({"age"}),
        removed=frozenset({"legacy"}),
        modified=frozenset({"name"}),
    )

    class _Renderer:
        def render(self, diff: Any) -> list[str]:
            return list(diff.added_fields)

    assert diff.render(_Renderer()) == ["age"]
