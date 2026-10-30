from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from pyverge.core.types import (
    ModelData,
    ModelHandle,
    VersionValue,
)
from pyverge.versioning import (
    Comparable,
    Diffable,
    FieldDescriptor,
    NodeId,
    Versionable,
    VersionKey,
)

if TYPE_CHECKING:
    from pyverge.versioning import Diff, ModelRef, VersionNode

#: Provider model TypeVars. These live outside core on purpose: core operates
#: on opaque :data:`ModelHandle` values, so no provider model base appears in a
#: core signature. The bounds stay ``type[Any]`` so a future non-Python backend
#: can map its own handle.
TContainer = TypeVar("TContainer")
VModel = TypeVar("VModel")
ProviderBase = TypeVar("ProviderBase")
ProviderBase_co = TypeVar("ProviderBase_co", covariant=True)
Container_co = TypeVar("Container_co", covariant=True)
VSource_co = TypeVar("VSource_co", covariant=True)
VTarget_co = TypeVar("VTarget_co", covariant=True)
VModel_co = TypeVar("VModel_co", covariant=True)


@runtime_checkable
class ModelIdentityPort(Protocol):
    """Provider identity and version/kind policy."""

    def model_id(self, handle: ModelHandle) -> str: ...
    def version(self, model_cls: ModelHandle) -> str: ...
    def kind(self, model_cls: ModelHandle) -> str: ...

    @property
    def version_property(self) -> str: ...

    @property
    def kind_property(self) -> str: ...

    def ref(self, handle: ModelHandle) -> ModelRef: ...


@runtime_checkable
class ModelSchemaPort(Protocol):
    """Provider-neutral schema reflection."""

    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]: ...
    def references(self, model_cls: ModelHandle) -> frozenset[NodeId]: ...

    def ensure_compatible(
        self,
        container: Any,
        *,
        fields: frozenset[str],
    ) -> None: ...


@runtime_checkable
class ModelRuntimePort(Protocol):
    """Runtime construction, validation, and handle resolution."""

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any: ...
    def dump(self, model: object) -> ModelData: ...
    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]: ...
    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]: ...
    def identify(self, model_cls: ModelHandle) -> bool: ...
    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool: ...
    def resolve(self, ref: ModelRef) -> ModelHandle: ...


@runtime_checkable
class ModelReflectionPort(Protocol):
    """Reflection from field annotations to provider handles."""

    def resolve_model(self, annotation: Any) -> ModelHandle | None: ...
    def field_model(
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None: ...


@runtime_checkable
class ModelMaterializationPort(Protocol[VersionValue]):
    """Graph materialization and diff construction."""

    def versionable(
        self,
        model_cls: ModelHandle,
        *,
        kind: str | None = None,
        version: str | None = None,
    ) -> VersionNode[VersionValue]: ...

    def version_key(
        self,
        *,
        kind: str,
        version: str,
    ) -> VersionKey[VersionValue]: ...

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Diff[VersionValue]: ...

    def materialize(
        self, diff: Diffable[VersionValue]
    ) -> VersionNode[VersionValue]: ...


@runtime_checkable
class ModelAdapter(
    ModelIdentityPort,
    ModelSchemaPort,
    ModelRuntimePort,
    ModelReflectionPort,
    ModelMaterializationPort[VersionValue],
    Protocol[VersionValue],
):
    """Composed provider seam built from the narrower capability ports."""


__all__ = [
    "Container_co",
    "ModelAdapter",
    "ModelIdentityPort",
    "ModelMaterializationPort",
    "ModelReflectionPort",
    "ModelRuntimePort",
    "ModelSchemaPort",
    "ProviderBase",
    "ProviderBase_co",
    "TContainer",
    "VModel",
    "VModel_co",
    "VSource_co",
    "VTarget_co",
]
