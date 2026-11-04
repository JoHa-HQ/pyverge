from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    Self,
    TypeAlias,
    runtime_checkable,
)

from pyverge.core.types import JsonValue

from ..frozen import FrozenMap

if TYPE_CHECKING:
    from .nodes import NodeId

MetadataValue = Any


@runtime_checkable
class HashingProvider(Protocol):
    """Anything that can hash a canonical value."""

    def digest(self, value: Any) -> str: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class KeyRef:
    """Agnostic, immutable metadata attached to graph keys.

    Refs describe node or edge content. They do not identify a package, an
    artifact location, or a runtime capability.
    """

    metadata: Mapping[str, MetadataValue] = field(
        default_factory=dict,
        compare=False,
        hash=False,
        repr=False,
    )

    def get(self, key: str, default: MetadataValue = None) -> MetadataValue:
        return self.metadata.get(key, default)

    def merged(self, **values: MetadataValue) -> Self:
        return replace(self, metadata={**self.metadata, **values})

    def to_canonical(self) -> Mapping[str, Any]:
        if not self.metadata:
            return {}
        return {"metadata": dict(self.metadata)}

    @classmethod
    def from_canonical(cls, value: Mapping[str, Any]) -> Self:
        return cls(metadata=dict(value.get("metadata", {})))

    def digest(self, hashing: HashingProvider) -> str:
        return hashing.digest(self.to_canonical())


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeRef(KeyRef):
    """Generic metadata for any node key.

    NodeRef does not require provider or model identity. Hydrated model nodes
    use :class:`ModelRef`, which extends this ref. A key-only entry may still
    carry a ModelRef when the lock provides one, because ModelRef is a NodeRef.
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRef(NodeRef):
    """A node ref for a hydrated model with provider and entity identity."""

    provider_id: str
    entity_id: str

    def to_canonical(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "provider_id": self.provider_id,
            "entity_id": self.entity_id,
        }
        if self.metadata:
            value["metadata"] = dict(self.metadata)
        return value

    @classmethod
    def from_canonical(cls, value: Mapping[str, Any]) -> ModelRef:
        provider_id = value.get("provider_id", value.get("provider"))
        entity_id = value.get("entity_id", value.get("model_id"))
        if provider_id is None or entity_id is None:
            raise ValueError("ModelRef requires provider_id and entity_id")
        return cls(
            provider_id=str(provider_id),
            entity_id=str(entity_id),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class EdgeRef(KeyRef):
    """Generic metadata for an edge key."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MigrationRef(EdgeRef):
    """Metadata for a migration artifact."""

    provider_id: str
    entity_id: str

    def to_canonical(self) -> Mapping[str, Any]:
        value: dict[str, Any] = {
            "provider_id": self.provider_id,
            "entity_id": self.entity_id,
        }
        if self.metadata:
            value["metadata"] = dict(self.metadata)
        return value

    @classmethod
    def from_canonical(cls, value: Mapping[str, Any]) -> Self:
        return cls(
            provider_id=str(value["provider_id"]),
            entity_id=str(value["entity_id"]),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class HookRef(EdgeRef):
    """Metadata for an edge hook."""

    provider_id: str
    entity_id: str
    config: Mapping[str, MetadataValue] = field(compare=False, hash=False)

    def to_canonical(self) -> Mapping[str, Any]:
        value: dict[str, Any] = {
            "provider_id": self.provider_id,
            "entity_id": self.entity_id,
            "config": dict(self.config),
        }
        if self.metadata:
            value["metadata"] = dict(self.metadata)
        return value

    @classmethod
    def from_canonical(cls, value: Mapping[str, Any]) -> Self:
        return cls(
            provider_id=str(value["provider_id"]),
            entity_id=str(value["entity_id"]),
            config=dict(value["config"]),
            metadata=dict(value.get("metadata", {})),
        )


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
class MigrationDescriptor:
    """Provider-neutral, serializable identity of one executable migration."""

    strategy: str
    identity: str

    @property
    def provider_id(self) -> str:
        return self.strategy

    @property
    def entity_id(self) -> str:
        return self.identity

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
        from .nodes import NodeId  # noqa: PLC0415

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
    "EdgeRef",
    "FieldDescriptor",
    "HashingProvider",
    "HookRef",
    "KeyRef",
    "MetadataValue",
    "MigrationDescriptor",
    "MigrationRef",
    "ModelDescriptor",
    "ModelRef",
    "NoDefault",
    "NodeRef",
    "TypeKind",
    "TypeRef",
]
