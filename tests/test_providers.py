"""Schema provider, diff provider, and materializer contract tests."""

from __future__ import annotations

import pendulum
import pytest
from pydantic import ValidationError

from pyverge.discovery.reflection import CompositeDiffDiscovery, Reflection
from pyverge.engine import Engine
from pyverge.migrations.json_patch.backend import JsonPatchMigrationBackend
from pyverge.providers import JsonPatchMigration
from pyverge.schemas import (
    DataclassModelAdapter,
    JsonSchemaModelAdapter,
    ModelCodec,
    PydanticModelAdapter,
)
from pyverge.settings import MigrationSettings, VersioningSettings
from pyverge.versioning import (
    Diff,
    DiffOrigin,
    EdgeKey,
    FieldChange,
    FieldDescriptor,
    FieldStatus,
    FrozenMap,
    TypeRef,
)
from tests.examples.dataclasses import (
    AddressV1,
    ContactV1,
    PersonV1,
    RequiredValue,
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
        PydanticModelAdapter(codec=ModelCodec()),
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
        JsonSchemaModelAdapter(codec=ModelCodec()),
        USER_V1_0_0,
        USER_V2_0_0,
        {"kind": "User", "version": "1.0.0", "name": "Alice"},
        id="json_schema",
    ),
    pytest.param(
        DataclassModelAdapter(codec=ModelCodec()),
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
    assert "version" not in adapter.fields(adapter.resolve(node.descriptor.ref))
    assert adapter.model_codec.version_property == "version"
    assert adapter.model_codec.kind_property == "kind"
    assert adapter.identify(adapter.resolve(node.descriptor.ref))
    assert adapter.can_handle(adapter.resolve(node.descriptor.ref))
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
    node = adapter.materialize(adapter.diff(source, target))
    assert node.version == target.version


@pytest.mark.parametrize(
    ("adapter", "source_model", "target_model", "payload"), ADAPTERS
)
def test_diff_provider(adapter, source_model, target_model, payload):
    reflection = Reflection(adapter, CompositeDiffDiscovery())
    source = adapter.versionable(source_model)
    target = adapter.versionable(target_model)
    assert reflection.diff(source, target).origin == "schema"


def test_diff_origin_from_migration():
    adapter = PydanticModelAdapter(codec=ModelCodec())
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

    reconstructed_model = engine.adapter.resolve(reconstructed.descriptor.ref)
    assert reconstructed_model is not None
    assert "age" not in reconstructed_model.model_fields


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


@pytest.fixture
def dataclass_adapter() -> DataclassModelAdapter:
    return DataclassModelAdapter(codec=ModelCodec())


@pytest.mark.parametrize(
    ("model", "kind", "version", "fields"),
    [
        pytest.param(
            PersonV1,
            "Person",
            "1.0.0",
            {"name", "address", "contacts"},
            id="person",
        ),
    ],
)
def test_dataclass_identity(
    dataclass_adapter: DataclassModelAdapter,
    model: type,
    kind: str,
    version: str,
    fields: set[str],
) -> None:
    assert dataclass_adapter.version(model) == version
    assert dataclass_adapter.kind(model) == kind
    assert dataclass_adapter.identify(model)
    assert dataclass_adapter.fields(model) == fields


def test_dataclass_dump(dataclass_adapter: DataclassModelAdapter) -> None:
    assert not dataclass_adapter.identify(int)
    assert dataclass_adapter.dump(PersonV1(name="Alice"))["name"] == "Alice"
    with pytest.raises(TypeError, match="expected a dataclass"):
        dataclass_adapter.dump({"name": "Alice"})


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        pytest.param("address", AddressV1, id="nested"),
        pytest.param("contacts", ContactV1, id="list"),
        pytest.param("name", None, id="scalar"),
        pytest.param("missing", None, id="missing"),
    ],
)
def test_dataclass_field_models(
    dataclass_adapter: DataclassModelAdapter,
    field: str,
    expected: type | None,
) -> None:
    assert dataclass_adapter.can_handle(PersonV1)
    assert not dataclass_adapter.can_handle(dict)
    assert dataclass_adapter.can_handle(PersonV1, fields=frozenset({"street"}))
    assert not dataclass_adapter.can_handle(PersonV1, fields=frozenset({"missing"}))
    assert dataclass_adapter.field_model(PersonV1, field) is expected


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        pytest.param(AddressV1, AddressV1, id="model"),
        pytest.param(list[AddressV1], AddressV1, id="list"),
        pytest.param(AddressV1 | None, AddressV1, id="optional"),
        pytest.param(int, None, id="unsupported"),
    ],
)
def test_dataclass_resolve_model(
    dataclass_adapter: DataclassModelAdapter,
    annotation: object,
    expected: type | None,
) -> None:
    assert dataclass_adapter.resolve_model(annotation) is expected


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        pytest.param(
            PersonV1,
            {("Address", "1.0.0"), ("Contact", "1.0.0")},
            id="person",
        ),
    ],
)
def test_dataclass_references(
    dataclass_adapter: DataclassModelAdapter,
    model: type,
    expected: set[tuple[str, str]],
) -> None:
    assert {
        (kind, str(version)) for kind, version in dataclass_adapter.references(model)
    } == expected


def test_dataclass_instantiate_nested_lists_defaults_and_errors(
    dataclass_adapter: DataclassModelAdapter,
) -> None:
    person = dataclass_adapter.instantiate(
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
    assert dataclass_adapter.finalize(PersonV1, {"name": "Bob"})["name"] == "Bob"
    assert dataclass_adapter.validate({"name": "Cara"}, PersonV1)["name"] == "Cara"
    with pytest.raises(ValidationError, match="Field required"):
        dataclass_adapter.instantiate(RequiredValue, {})


def test_dataclass_describe_fields_and_materialize(
    dataclass_adapter: DataclassModelAdapter,
) -> None:
    described = dataclass_adapter.describe_fields(PersonV1)
    assert described["name"].type_ref == TypeRef.primitive("string")
    assert not described["name"].required
    assert not described["address"].required
    assert described["address"].default == {
        "kind": "Address",
        "version": "1.0.0",
        "street": "",
    }
    assert dataclass_adapter.describe_fields(RequiredValue)["value"].required

    source = dataclass_adapter.versionable(PersonV1)
    target = dataclass_adapter.version_key(kind="Person", version="2.0.0")
    diff = Diff(
        source=source,
        target=target,
        fields=FrozenMap(),
        origin=DiffOrigin.SCHEMA,
    )
    materialized = dataclass_adapter.materialize_model(diff)
    node = dataclass_adapter.versionable(materialized)
    assert node.kind == "Person"
    assert str(node.version[1]) == "2.0.0"
    assert "name" in dataclass_adapter.fields(materialized)
    assert EdgeKey.from_pair(source, node)


def test_dataclass_materialize_with_added_and_defaulted_fields(
    dataclass_adapter: DataclassModelAdapter,
) -> None:
    source = dataclass_adapter.versionable(AddressV1)
    target = dataclass_adapter.version_key(kind="Address", version="2.0.0")
    diff = Diff(
        source=source,
        target=target,
        fields=FrozenMap(
            {
                "zip": FieldChange(
                    FieldStatus.ADDED, {"type": str, "default": "00000"}
                ),
                "country": FieldChange(
                    FieldStatus.ADDED, {"type": str, "required": True}
                ),
            }
        ),
        origin=DiffOrigin.SCHEMA,
    )
    materialized = dataclass_adapter.materialize_model(diff)
    instance = materialized(zip="12345", country="DE")
    assert instance.zip == "12345"
    assert instance.country == "DE"


def test_model_codec_identity_operations() -> None:
    codec = ModelCodec(version_property="v", kind_property="k")
    fields = FrozenMap(
        {
            "v": FieldDescriptor(
                name="v", type_ref=TypeRef.primitive("string"), default="1.2.3"
            ),
            "k": FieldDescriptor(
                name="k", type_ref=TypeRef.primitive("string"), default="User"
            ),
        }
    )

    assert codec.version(fields) == "1.2.3"
    assert codec.kind(fields) == "User"
    assert codec.of("2024-01-01") == pendulum.Date(2024, 1, 1)
    assert codec.version_key(kind="User", version="1.2.3").jgf_id == "User@1.2.3"
    with pytest.raises(ValueError, match="Cannot parse version"):
        codec.of("not-a-version")
