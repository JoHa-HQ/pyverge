from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from pyverge.core.types import (
    Comparable,
    Diffable,
    ModelData,
    ModelHandle,
    ModelVersionKey,
    VersionValue,
    VersionValue_co,
)

if TYPE_CHECKING:
    from pyverge.core.versioning import VersionNode
    from pyverge.providers.json_patch.migration import JsonPatchMigration
    from pyverge.reflection.diff import Diff

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
class ModelAdapter(Protocol):
    """Provider-specific model operations.

    The single provider seam: the migration engine and registry stay
    provider-agnostic and reach every provider concern through this protocol.
    Implementations are provided for each supported model provider (Pydantic,
    JSON Schema, ...).
    """

    def version(self, model_cls: ModelHandle) -> str: ...
    def kind(self, model_cls: ModelHandle) -> str: ...
    @property
    def version_property(self) -> str:
        """The field name carrying a model's version."""
        ...

    @property
    def kind_property(self) -> str:
        """The field name carrying a model's kind."""
        ...

    def of(self, value: str | VersionValue) -> VersionValue:
        """Parse a version string, or pass through an already-parsed value.

        Understands both semver and ISO date strings.  Idempotent: an existing
        ``VersionValue`` is returned unchanged.
        """
        ...

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
    def references(self, model_cls: ModelHandle) -> frozenset[ModelVersionKey]:
        """Return every versioned ``(kind, version)`` the model's fields declare.

        Walks annotations recursively and collects **all** model classes they
        mention — every ``Union`` member, ``list`` items — not just the first,
        so a model declaring several versions of a nested kind reports all.
        """
        ...

    def ensure_compatible(
        self,
        container: Any,
        *,
        fields: frozenset[str],
    ) -> None:
        """Raise when *container* cannot cover the migrated *fields*.

        The adapter owns container compatibility: it knows which model shapes
        it recognizes and which fields they declare.
        """
        ...

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool:
        """Report whether *container* is a recognized model/container type.

        With *fields*, also report whether the container covers those migrated
        field names.  One predicate serves both the walker's type gate
        (``fields=None``) and the pre-execution field gate.
        """
        ...

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any:
        """Build a typed container instance from a migrated payload."""
        ...

    def dump(self, model: object) -> ModelData:
        """Serialize a provider model into a payload mapping.

        The inverse of :meth:`instantiate`. Used where a typed instance (e.g. a
        handler's return value) must become a payload again before it can be
        converged or published.
        """
        ...

    def identify(self, model_cls: ModelHandle) -> bool:
        """Return whether the provider owns *model_cls*.

        A truthy identification is usable for a neutral store lookup; a falsey
        value means the class is unknown to this provider.
        """
        ...

    def versionable(
        self,
        model_cls: ModelHandle,
        *,
        kind: str | None = None,
        version: str | None = None,
    ) -> VersionNode[VersionValue]:
        """Wrap a model class into a materialized version node.

        ``kind`` and ``version`` are read from the class when omitted.
        """
        ...

    def version_key(
        self,
        *,
        kind: str,
        version: str,
    ) -> Comparable[VersionValue]:
        """Build a temporary search key from *kind* and *version* strings."""
        ...

    def diff(
        self,
        source: Comparable[VersionValue_co],
        target: Comparable[VersionValue_co],
        *,
        is_backward_compatible: bool = False,
    ) -> Diff[VersionValue_co]: ...

    def materialize_model(
        self,
        diff: Diffable[VersionValue_co],
    ) -> ModelHandle:
        """Materialize a model from a diff.

        The anchor is the diff's concrete ``source`` model and the version is
        the diff's ``target`` version.  The returned model conforms to this
        provider.
        """
        ...

    def materialize_migration(
        self,
        diff: Diffable[VersionValue_co],
    ) -> JsonPatchMigration:
        """Materialize a declarative migration from a diff.

        Reads the diff's ``source``/``target`` version identity and renders the
        structural change into an RFC 6902 :class:`JsonPatchMigration`.
        """
        ...
