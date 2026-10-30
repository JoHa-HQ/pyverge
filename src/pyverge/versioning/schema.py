from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self, TypeAlias

from pyverge.core.types import JsonValue

from .frozen import FrozenMap
from .identity import NodeId


class TypeKind(StrEnum):
    """Canonical type-reference kinds shared across providers."""

    ANY = "any"
    NULL = "null"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    BYTES = "bytes"
    ARRAY = "array"
    OBJECT = "object"
    MAP = "map"
    UNION = "union"
    LITERAL = "literal"
    MODEL = "model"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ModelRef:
    """Serializable provider reference to a model."""

    provider: str
    model_id: str

    def to_canonical(self) -> dict[str, str]:
        return {"model_id": self.model_id, "provider": self.provider}

    @classmethod
    def from_canonical(cls, value: Mapping[str, Any]) -> ModelRef:
        return cls(provider=str(value["provider"]), model_id=str(value["model_id"]))


@dataclass(frozen=True, slots=True)
class MigrationDescriptor:
    """Provider-neutral, serializable identity of one executable migration."""

    strategy: str
    identity: str

    def to_canonical(self) -> dict[str, str]:
        return {"strategy": self.strategy, "identity": self.identity}

    @classmethod
    def from_canonical(cls, value: Mapping[str, Any]) -> MigrationDescriptor:
        return cls(
            strategy=str(value["strategy"]),
            identity=str(value["identity"]),
        )


@dataclass(frozen=True, slots=True)
class NoDefault:
    """Marker for a field without a declared default.

    This is schema vocabulary, not a canonical value.  Descriptors omit the
    ``default`` key when this marker is present.
    """


NO_DEFAULT = NoDefault()
DefaultValue: TypeAlias = JsonValue | NoDefault


@dataclass(frozen=True, slots=True)
class TypeRef:
    """Canonical, serializable description of a field type."""

    kind: TypeKind
    item: TypeRef | None = None
    args: tuple[TypeRef, ...] = ()
    fields: FrozenMap[str, TypeRef] | None = None
    ref: ModelRef | None = None
    version: str | None = None
    values: tuple[Any, ...] = ()
    name: str | None = None

    @classmethod
    def any(cls) -> TypeRef:
        return cls(TypeKind.ANY)

    @classmethod
    def null(cls) -> TypeRef:
        return cls(TypeKind.NULL)

    @classmethod
    def primitive(cls, kind: TypeKind | str) -> TypeRef:
        return cls(TypeKind(kind))

    @classmethod
    def array(cls, item: TypeRef) -> TypeRef:
        return cls(TypeKind.ARRAY, item=item)

    @classmethod
    def object(cls, fields: Mapping[str, TypeRef]) -> TypeRef:
        return cls(TypeKind.OBJECT, fields=FrozenMap(fields))

    @classmethod
    def mapping(cls, key: TypeRef, value: TypeRef) -> TypeRef:
        return cls(TypeKind.MAP, args=(key, value))

    @classmethod
    def union(cls, *args: TypeRef) -> TypeRef:
        return cls(TypeKind.UNION, args=tuple(args))

    @classmethod
    def literal(cls, *values: Any) -> TypeRef:
        return cls(TypeKind.LITERAL, values=tuple(values))

    @classmethod
    def model(cls, ref: ModelRef, *, version: str | None = None) -> TypeRef:
        return cls(TypeKind.MODEL, ref=ref, version=version)

    @classmethod
    def unknown(cls, name: str) -> TypeRef:
        return cls(TypeKind.UNKNOWN, name=name)

    @classmethod
    def from_canonical(cls, value: Mapping[str, Any]) -> TypeRef:
        fields = value.get("fields")
        return cls(
            kind=TypeKind(value["kind"]),
            name=None if value.get("name") is None else str(value["name"]),
            item=(
                None if value.get("item") is None else cls.from_canonical(value["item"])
            ),
            args=tuple(cls.from_canonical(arg) for arg in value.get("args", ())),
            fields=(
                None
                if fields is None
                else FrozenMap(
                    {str(key): cls.from_canonical(item) for key, item in fields.items()}
                )
            ),
            ref=(
                None
                if value.get("ref") is None
                else ModelRef.from_canonical(value["ref"])
            ),
            version=(None if value.get("version") is None else str(value["version"])),
            values=tuple(value.get("values", ())),
        )

    def to_canonical(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind.value}
        if self.name is not None:
            payload["name"] = self.name
        if self.item is not None:
            payload["item"] = self.item.to_canonical()
        if self.args:
            payload["args"] = [arg.to_canonical() for arg in self.args]
        if self.fields is not None:
            payload["fields"] = {
                key: value.to_canonical() for key, value in self.fields.sorted_items()
            }
        if self.ref is not None:
            payload["ref"] = self.ref.to_canonical()
        if self.version is not None:
            payload["version"] = self.version
        if self.values:
            payload["values"] = list(self.values)
        return payload


@dataclass(frozen=True, slots=True)
class FieldDescriptor:
    """Provider-neutral description of one model field."""

    name: str
    type_ref: TypeRef
    required: bool = False
    default: DefaultValue = NO_DEFAULT
    references: tuple[NodeId, ...] = ()
    annotation: Any = field(default=None, compare=False, repr=False)

    @classmethod
    def from_canonical(
        cls,
        value: Mapping[str, Any],
        *,
        parse_version: Callable[[str], Any],
    ) -> FieldDescriptor:
        references = tuple(
            NodeId(
                namespace=str(item["namespace"]),
                kind=str(item["kind"]),
                version=parse_version(str(item["version"])),
            )
            for item in value.get("references", ())
        )
        default: DefaultValue = (
            NO_DEFAULT if "default" not in value else value["default"]
        )
        return cls(
            name=str(value["name"]),
            type_ref=TypeRef.from_canonical(value["type_ref"]),
            required=bool(value.get("required", False)),
            default=default,
            references=references,
        )

    def to_canonical(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "required": self.required,
            "type_ref": self.type_ref.to_canonical(),
        }
        if self.references:
            payload["references"] = [
                {
                    "namespace": reference.namespace,
                    "kind": reference.kind,
                    "version": str(reference.version),
                }
                for reference in self.references
            ]
        if not isinstance(self.default, NoDefault):
            payload["default"] = self.default
        return payload


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """Provider-neutral, serializable model surface."""

    ref: ModelRef
    fields: FrozenMap[str, FieldDescriptor]

    @property
    def references(self) -> frozenset[NodeId]:
        return frozenset(
            reference
            for descriptor in self.fields.values()
            for reference in descriptor.references
        )

    def with_ref(self, ref: ModelRef) -> Self:
        return type(self)(ref=ref, fields=self.fields)

    def with_fields(self, *fields: FieldDescriptor) -> Self:
        return type(self)(
            ref=self.ref,
            fields=self.fields.updated(
                {descriptor.name: descriptor for descriptor in fields}
            ),
        )

    def without_fields(self, *names: str) -> Self:
        return type(self)(ref=self.ref, fields=self.fields.removed(names))

    @classmethod
    def from_canonical(
        cls,
        value: Mapping[str, Any],
        *,
        parse_version: Callable[[str], Any],
    ) -> ModelDescriptor:
        return cls(
            ref=ModelRef.from_canonical(value["ref"]),
            fields=FrozenMap(
                {
                    str(name): FieldDescriptor.from_canonical(
                        item, parse_version=parse_version
                    )
                    for name, item in value.get("fields", {}).items()
                }
            ),
        )

    def to_canonical(self) -> dict[str, Any]:
        return {
            "ref": self.ref.to_canonical(),
            "fields": {
                name: descriptor.to_canonical()
                for name, descriptor in self.fields.sorted_items()
            },
            "references": [
                {
                    "namespace": reference.namespace,
                    "kind": reference.kind,
                    "version": str(reference.version),
                }
                for reference in sorted(
                    self.references,
                    key=lambda item: (item.namespace, item.kind, str(item.version)),
                )
            ],
        }


__all__ = [
    "NO_DEFAULT",
    "DefaultValue",
    "FieldDescriptor",
    "MigrationDescriptor",
    "ModelDescriptor",
    "ModelRef",
    "NoDefault",
    "TypeKind",
    "TypeRef",
]
