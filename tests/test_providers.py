"""Schema provider, diff provider, and materializer contract tests."""

from __future__ import annotations

import pytest

from pyverge.discovery.reflection import CompositeDiffDiscovery, Reflection
from pyverge.engine import Engine
from pyverge.migrations.json_patch.backend import JsonPatchMigrationBackend
from pyverge.providers import (
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    PydanticModelAdapter,
)
from pyverge.schemas import DataclassModelAdapter
from pyverge.schemas.backend import ModelMaterializer
from pyverge.settings import MigrationSettings, VersioningSettings
from pyverge.versioning import Diff, DiffOrigin, EdgeKey, FieldChange, FieldStatus
from tests.examples.dataclasses import (
    AddressV1,
    ContactV1,
    DuplicateAddresses,
    FactoryIdentity,
    MixedReferences,
    PersonV1,
    RequiredValue,
    WithInitFalse,
)
from tests.examples.dataclasses import (
    UserV1 as DataclassUserV1,
)
from tests.examples.dataclasses import (
    UserV2 as DataclassUserV2,
)
from tests.examples.json import USER_V1_0_0, USER_V2_0_0
from tests.examples.pydantic.semver import UserV1, UserV2
from tests.utils import envelope_model, meta_versionable


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
    assert engine.registry.migrations_of(anchor) == frozenset()


def test_default_factory_identity() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.kind(FactoryIdentity) == "FactoryIdentity"
    assert adapter.version(FactoryIdentity) == "1.0.0"


def test_identity_fields_and_dump() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.version(PersonV1) == "1.0.0"
    assert adapter.kind(PersonV1) == "Person"
    assert adapter.identify(PersonV1)
    assert not adapter.identify(int)
    assert adapter.fields(PersonV1) == {"name", "address", "contacts"}
    assert adapter.dump(PersonV1(name="Alice"))["name"] == "Alice"
    with pytest.raises(TypeError, match="expected a dataclass"):
        adapter.dump({"name": "Alice"})


def test_can_handle_and_field_models() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.can_handle(PersonV1)
    assert not adapter.can_handle(dict)
    assert adapter.can_handle(PersonV1, fields=frozenset({"street"}))
    assert not adapter.can_handle(PersonV1, fields=frozenset({"missing"}))
    assert adapter.field_model(PersonV1, "address") is AddressV1
    assert adapter.field_model(PersonV1, "contacts") is ContactV1
    assert adapter.field_model(PersonV1, "name") is None
    assert adapter.field_model(PersonV1, "missing") is None


def test_resolve_model_and_references() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.resolve_model(AddressV1) is AddressV1
    assert adapter.resolve_model(list[AddressV1]) is AddressV1
    assert adapter.resolve_model(AddressV1 | None) is AddressV1
    assert adapter.resolve_model(int) is None
    assert adapter.references(PersonV1) == {
        ("Address", adapter.of("1.0.0")),
        ("Contact", adapter.of("1.0.0")),
    }


def test_reference_edge_cases() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.references(int) == frozenset()
    assert adapter.references(DuplicateAddresses) == {
        ("Address", adapter.of("1.0.0")),
    }
    assert adapter.references(MixedReferences) == {("Node", adapter.of("1.0.0"))}


def test_coerce_existing_none_union_and_init_false() -> None:
    adapter = DataclassModelAdapter()
    address = AddressV1(street="Main")
    person = adapter.instantiate(PersonV1, {"address": address})
    assert person.address is address
    assert adapter.instantiate(PersonV1, {"address": None}).address is None
    init_false = adapter.instantiate(WithInitFalse, {"kind": "WithInitFalse"})
    assert init_false.value == 0


def test_diff_without_target_model() -> None:
    adapter = DataclassModelAdapter()
    source = adapter.versionable(AddressV1)
    target = adapter.version_key(kind="Address", version="2.0.0")
    assert adapter.diff(source, target).fields == {}


def test_instantiate_nested_lists_defaults_and_errors() -> None:
    adapter = DataclassModelAdapter()
    person = adapter.instantiate(
        PersonV1,
        {
            "name": "Alice",
            "address": {"street": "Main"},
            "contacts": [{"phone": "123"}],
        },
    )
    assert isinstance(person.address, AddressV1)
    assert person.address.street == "Main"
    assert isinstance(person.contacts[0], ContactV1)
    assert person.contacts[0].phone == "123"
    assert adapter.finalize(PersonV1, {"name": "Bob"})["name"] == "Bob"
    assert adapter.validate({"name": "Cara"}, PersonV1)["name"] == "Cara"
    with pytest.raises(TypeError, match="Missing required dataclass field"):
        adapter.instantiate(RequiredValue, {})


def test_describe_fields_and_materialize() -> None:
    adapter = DataclassModelAdapter()
    described = adapter.describe_fields(PersonV1)
    assert not described["name"].required
    assert not described["address"].required
    assert described["address"].default == AddressV1()
    assert adapter.describe_fields(RequiredValue)["value"].required

    source = adapter.versionable(PersonV1)
    target = adapter.version_key(kind="Person", version="2.0.0")
    diff = Diff(
        source=source,
        target=target,
        fields={},
        origin=DiffOrigin.SCHEMA,
    )
    materialized = adapter.materialize_model(diff)
    node = adapter.versionable(materialized)
    assert node.kind == "Person"
    assert str(node.version[1]) == "2.0.0"
    assert "name" in adapter.fields(materialized)
    assert EdgeKey.from_pair(source, node)


def test_materialize_with_added_and_defaulted_fields() -> None:
    adapter = DataclassModelAdapter()
    source = adapter.versionable(AddressV1)
    target = adapter.version_key(kind="Address", version="2.0.0")
    diff = Diff(
        source=source,
        target=target,
        fields={
            "zip": FieldChange(FieldStatus.ADDED, {"type": str, "default": "00000"}),
            "country": FieldChange(FieldStatus.ADDED, {"type": str, "required": True}),
        },
        origin=DiffOrigin.SCHEMA,
    )
    materialized = adapter.materialize_model(diff)
    instance = materialized(zip="12345", country="DE")
    assert instance.zip == "12345"
    assert instance.country == "DE"
