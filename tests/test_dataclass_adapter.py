"""Dataclass model adapter edge cases."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from pyverge.schemas import DataclassModelAdapter
from pyverge.versioning import Diff, DiffOrigin, EdgeKey, FieldChange, FieldStatus


@dataclass
class Address:
    kind: str = "Address"
    version: str = "1.0.0"
    street: str = ""


@dataclass
class Contact:
    kind: str = "Contact"
    version: str = "1.0.0"
    phone: str = ""


@dataclass
class Person:
    kind: str = "Person"
    version: str = "1.0.0"
    name: str = ""
    address: Address = field(default_factory=Address)
    contacts: list[Contact] | None = None


@dataclass
class Missing:
    value: int
    kind: str = field(default="Missing", kw_only=True)
    version: str = field(default="1.0.0", kw_only=True)


@dataclass
class FactoryIdentity:
    kind: str = field(default_factory=lambda: "Factory")
    version: str = field(default_factory=lambda: "1.0.0")


@dataclass
class NoKind:
    version: str = "1.0.0"


@dataclass
class BadVersion:
    kind: str = "Bad"
    version: str = "nope"


@dataclass
class Node:
    kind: str = "Node"
    version: str = "1.0.0"
    child: Node | None = None


@dataclass
class Duplicate:
    kind: str = "Duplicate"
    version: str = "1.0.0"
    first: Address = field(default_factory=Address)
    second: Address = field(default_factory=Address)


@dataclass
class WithInitFalse:
    kind: str = "WithInitFalse"
    version: str = "1.0.0"
    value: int = field(default=0, init=False)


@dataclass
class Mixed:
    kind: str = "Mixed"
    version: str = "1.0.0"
    no_kind: NoKind = field(default_factory=NoKind)
    bad: BadVersion = field(default_factory=BadVersion)
    node: Node = field(default_factory=Node)


def test_default_factory_identity() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.kind(FactoryIdentity) == "Factory"
    assert adapter.version(FactoryIdentity) == "1.0.0"


def test_identity_fields_and_dump() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.version(Person) == "1.0.0"
    assert adapter.kind(Person) == "Person"
    assert adapter.identify(Person)
    assert not adapter.identify(int)
    assert adapter.fields(Person) == {"name", "address", "contacts"}
    assert adapter.dump(Person(name="Alice"))["name"] == "Alice"
    with pytest.raises(TypeError, match="expected a dataclass"):
        adapter.dump({"name": "Alice"})


def test_can_handle_and_field_models() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.can_handle(Person)
    assert not adapter.can_handle(dict)
    assert adapter.can_handle(Person, fields=frozenset({"street"}))
    assert not adapter.can_handle(Person, fields=frozenset({"missing"}))
    assert adapter.field_model(Person, "address") is Address
    assert adapter.field_model(Person, "contacts") is Contact
    assert adapter.field_model(Person, "name") is None
    assert adapter.field_model(Person, "missing") is None


def test_resolve_model_and_references() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.resolve_model(Address) is Address
    assert adapter.resolve_model(list[Address]) is Address
    assert adapter.resolve_model(Address | None) is Address
    assert adapter.resolve_model(int) is None
    assert adapter.references(Person) == {
        ("Address", adapter.of("1.0.0")),
        ("Contact", adapter.of("1.0.0")),
    }


def test_reference_edge_cases() -> None:
    adapter = DataclassModelAdapter()
    assert adapter.references(int) == frozenset()
    assert adapter.references(Duplicate) == {
        ("Address", adapter.of("1.0.0")),
    }
    assert adapter.references(Mixed) == {("Node", adapter.of("1.0.0"))}


def test_coerce_existing_none_union_and_init_false() -> None:
    adapter = DataclassModelAdapter()
    address = Address(street="Main")
    person = adapter.instantiate(Person, {"address": address})
    assert person.address is address
    assert adapter.instantiate(Person, {"address": None}).address is None
    init_false = adapter.instantiate(WithInitFalse, {"kind": "WithInitFalse"})
    assert init_false.value == 0


def test_diff_without_target_model() -> None:
    adapter = DataclassModelAdapter()
    source = adapter.versionable(Address)
    target = adapter.version_key(kind="Address", version="2.0.0")
    assert adapter.diff(source, target).fields == {}


def test_instantiate_nested_lists_defaults_and_errors() -> None:
    adapter = DataclassModelAdapter()
    person = adapter.instantiate(
        Person,
        {
            "name": "Alice",
            "address": {"street": "Main"},
            "contacts": [{"phone": "123"}],
        },
    )
    assert isinstance(person.address, Address)
    assert person.address.street == "Main"
    assert isinstance(person.contacts[0], Contact)
    assert person.contacts[0].phone == "123"
    assert adapter.finalize(Person, {"name": "Bob"})["name"] == "Bob"
    assert adapter.validate({"name": "Cara"}, Person)["name"] == "Cara"
    with pytest.raises(TypeError, match="Missing required dataclass field"):
        adapter.instantiate(Missing, {})


def test_describe_fields_and_materialize() -> None:
    adapter = DataclassModelAdapter()
    described = adapter.describe_fields(Person)
    assert not described["name"].required
    assert not described["address"].required
    assert described["address"].default == Address()
    assert adapter.describe_fields(Missing)["value"].required

    source = adapter.versionable(Person)
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
    source = adapter.versionable(Address)
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
