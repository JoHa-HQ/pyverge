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

#: Provider model TypeVars.  These live outside core on purpose: core operates
#: on opaque :data:`ModelHandle` values, so no provider model base appears in a
#: core signature.  The bounds stay ``type[Any]`` so a future non-Python backend
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
class ModelAdapter(Protocol[VersionValue]):
    """Provider-specific model operations.

    The single provider seam: the migration engine and registry stay
    provider-agnostic and reach every provider concern through this protocol.
    Implementations are provided for each supported model provider (Pydantic,
    JSON Schema, ...).
    """

    def model_id(self, handle: ModelHandle) -> str: ...
    def version(self, model_cls: ModelHandle) -> str: ...
    def kind(self, model_cls: ModelHandle) -> str: ...
    @property
    def version_property(self) -> str: ...

    @property
    def kind_property(self) -> str: ...

    def of(self, value: str | VersionValue) -> VersionValue: ...

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]: ...
    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]: ...
    def resolve_model(self, annotation: Any) -> ModelHandle | None: ...
    def field_model(
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None: ...
    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]: ...
    def references(self, model_cls: ModelHandle) -> frozenset[NodeId]: ...

    def ensure_compatible(
        self,
        container: Any,
        *,
        fields: frozenset[str],
    ) -> None: ...

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool: ...

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any: ...

    def dump(self, model: object) -> ModelData: ...

    def identify(self, model_cls: ModelHandle) -> bool: ...

    def ref(self, handle: ModelHandle) -> ModelRef: ...

    def resolve(self, ref: ModelRef) -> ModelHandle: ...

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

    def materialize_model(
        self,
        diff: Diffable[VersionValue],
    ) -> ModelHandle: ...

    def materialize(
        self, diff: Diffable[VersionValue]
    ) -> VersionNode[VersionValue]: ...
