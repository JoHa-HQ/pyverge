"""Schema provider, diff provider, and materializer contract tests."""

from __future__ import annotations

import pytest

from pyverge.migration import (
    Engine,
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    PydanticModelAdapter,
)
from pyverge.migrations.json_patch.backend import JsonPatchMigrationBackend
from pyverge.reflection import CompositeDiffDiscovery, Reflection
from pyverge.schemas import DataclassModelAdapter
from pyverge.schemas.backend import ModelMaterializer
from tests.examples.dataclasses import UserV1 as DataclassUserV1
from tests.examples.dataclasses import UserV2 as DataclassUserV2
from tests.examples.json import USER_V1_0_0, USER_V2_0_0
from tests.examples.pydantic.semver import UserV1, UserV2
from tests.utils import envelope_model, meta_versionable
from tests.utils.settings import MigrationSettings, VersioningSettings


def _add_age():
    return JsonPatchMigration(
        {
            "from": "1.0.0",
            "to": "2.0.0",
            "ops": [{"op": "add", "path": "/age", "value": None}],
        }
    ).patch


ADAPTERS = [
    pytest.param(
        PydanticModelAdapter(),
        UserV1,
        UserV2,
        {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        },
        id="pydantic",
    ),
    pytest.param(
        JsonSchemaModelAdapter(),
        USER_V1_0_0,
        USER_V2_0_0,
        {"kind": "User", "version": "1.0.0", "name": "Alice"},
        id="json_schema",
    ),
    pytest.param(
        DataclassModelAdapter(),
        DataclassUserV1,
        DataclassUserV2,
        {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "address": {"kind": "Address", "version": "1.0.0", "street": "Main"},
        },
        id="dataclass",
    ),
]


@pytest.mark.parametrize(
    ("adapter", "source_model", "target_model", "payload"), ADAPTERS
)
def test_adapter_identity_and_codec(adapter, source_model, target_model, payload):
    node = adapter.versionable(source_model)
    assert node.kind == "User"
    assert str(node.version[1]) == "1.0.0"
    assert "version" not in adapter.fields(node.model)
    if not isinstance(source_model, dict):
        instance = adapter.instantiate(source_model, payload)
        assert adapter.dump(instance)["kind"] == "User"


@pytest.mark.parametrize(
    ("adapter", "source_model", "target_model", "payload"), ADAPTERS
)
def test_adapter_diff_and_migration_materialization(
    adapter, source_model, target_model, payload
):
    source = adapter.versionable(source_model)
    target = adapter.versionable(target_model)
    diff = adapter.diff(source, target)
    assert diff.is_added("age")

    migration = diff.materialize(JsonPatchMigrationBackend())
    assert isinstance(migration, JsonPatchMigration)
    assert migration.spec["from"] == "1.0.0"
    assert migration.spec["to"] == "2.0.0"


@pytest.mark.parametrize(
    ("adapter", "source_model", "target_model", "payload"), ADAPTERS
)
def test_model_materializer(adapter, source_model, target_model, payload):
    source = adapter.versionable(source_model)
    target = adapter.versionable(target_model)
    node = ModelMaterializer(adapter).materialize(adapter.diff(source, target))
    assert node.version == target.version


@pytest.mark.parametrize(
    ("adapter", "source_model", "target_model", "payload"), ADAPTERS
)
def test_diff_provider(adapter, source_model, target_model, payload):
    reflection = Reflection(adapter, CompositeDiffDiscovery())
    source = adapter.versionable(source_model)
    target = adapter.versionable(target_model)
    assert reflection.diff(source, target).origin == "schema"


def test_dataclass_references() -> None:
    adapter = DataclassModelAdapter()
    assert {
        (kind, str(version)) for kind, version in adapter.references(DataclassUserV1)
    } == {("Address", "1.0.0")}


def test_diff_origin_from_migration():
    adapter = PydanticModelAdapter()
    reflection = Reflection(adapter, CompositeDiffDiscovery())
    v1 = envelope_model(adapter, MigrationSettings(), UserV1)
    v2 = envelope_model(adapter, MigrationSettings(), UserV2)
    assert reflection.diff(v2, v1, migration=_add_age()).origin == "migration"


@pytest.mark.parametrize(
    "migration_settings",
    [{"on_missing": "reconstruct_model"}],
    indirect=True,
)
def test_reconstructs_missing_model_on_store_migration(
    engine: Engine,
    model_adapter: PydanticModelAdapter,
    versioning_settings: VersioningSettings,
) -> None:
    real = envelope_model(model_adapter, versioning_settings, UserV2)
    engine.store_model(real)
    meta = meta_versionable(model_adapter, "User", "1.0.0")

    engine.store_migration(
        (meta, real),
        JsonPatchMigration(
            {
                "from": "1.0.0",
                "to": "2.0.0",
                "ops": [{"op": "add", "path": "/age", "value": None}],
            }
        ).patch,
    )
    reconstructed = engine.get_model(meta)

    assert reconstructed.model is not None
    assert "age" not in reconstructed.model.model_fields


@pytest.mark.parametrize(
    "migration_settings",
    [{"on_missing": "reconstruct_migration"}],
    indirect=True,
)
def test_proposes_migration_from_schema_diff(
    engine: Engine,
    model_adapter: PydanticModelAdapter,
    versioning_settings: VersioningSettings,
) -> None:
    anchor = envelope_model(model_adapter, versioning_settings, UserV1)
    target = envelope_model(model_adapter, versioning_settings, UserV2)
    engine.store_model(anchor)
    engine.store_model(target)

    migration = engine.propose_migration(anchor, target)

    assert isinstance(migration, JsonPatchMigration)
    assert migration.spec["from"] == "1.0.0"
    assert migration.spec["to"] == "2.0.0"
    assert {"op": "add", "path": "/age", "value": None} in migration.spec["ops"]
    assert engine.registry.migrations_of(anchor.kind) == frozenset()
