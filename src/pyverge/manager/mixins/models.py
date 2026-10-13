from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, cast, overload

from pyverge.core.types import (
    Comparable,
    ModelData,
    ModelKey,
    ModelKind,
    ModelVersionKey,
    Versionable,
    VersionValue,
)
from pyverge.core.versioning import (
    VersionNode,
)
from pyverge.providers.types import (
    ModelHandle,
)

if TYPE_CHECKING:
    from pyverge.migration.engine import Engine

    from . import ManagerState


class ModelStoreMixin(Generic[VersionValue]):
    """Store and look up registered model versions."""

    @singledispatchmethod
    @classmethod
    def store_model(
        cls: type[ManagerState[VersionValue]],
        key: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        """Register a model version through the engine."""
        engine = engine or cls._default_engine
        return engine.store_model(engine.adapter.versionable(key))

    @store_model.register(VersionNode)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        version: VersionNode[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        """Register an already-built versionable (strict; duplicates fail)."""
        engine = engine or cls._default_engine
        return engine.store_model(version)

    @singledispatchmethod
    @classmethod
    def reconcile_model(
        cls: type[ManagerState[VersionValue]],
        key: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        """Register a model, reconciling an identical re-registration.

        The idempotent fallback to :meth:`store_model`: an identical surface is
        a no-op, a differing one raises :class:`ModelConflictError`.
        """
        engine = engine or cls._default_engine
        return engine.reconcile_model(engine.adapter.versionable(key))

    @reconcile_model.register(VersionNode)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        version: VersionNode[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return engine.reconcile_model(version)

    def missing_references(
        self: ManagerState[VersionValue],
        version: Versionable[VersionValue],
    ) -> frozenset[ModelVersionKey]:
        """Return the versioned ``(kind, version)`` pairs *version* declares
        but that are not registered."""
        return self.engine.registry.missing_references(version)

    def validate_graph(
        self: ManagerState[VersionValue],
        version: Versionable[VersionValue] | None = None,
    ) -> None:
        """Validate registered models' declared references are registered.

        Raises :class:`~pyverge.core.MissingReferenceError` on the first model
        that references an unregistered versioned kind.
        """
        self.engine.validate(version)

    @classmethod
    def list_versions(
        cls: type[ManagerState[VersionValue]],
        kind: ModelKind | None = None,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> list[Versionable[VersionValue]]:
        """Return registered versions, optionally filtered by *kind*."""
        engine = engine or cls._default_engine
        if kind is None:
            return engine.registry.versions
        return engine.registry.kind_versions(kind)

    @classmethod
    def get_entities(
        cls: type[ManagerState[VersionValue]],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> list[ModelKind]:
        """Return the kinds that have at least one registered version."""
        engine = engine or cls._default_engine
        return engine.get_entities()

    @classmethod
    def identifies(
        cls: type[ManagerState[VersionValue]],
        key: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> bool:
        """Return whether *key* is a versionable model this manager can handle."""
        engine = engine or cls._default_engine
        return engine.adapter.identify(key)

    @classmethod
    def dump(
        cls: type[ManagerState[VersionValue]],
        value: object,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> ModelData:
        """Return *value* as a payload mapping.

        A mapping passes through; a provider model is serialized by the adapter
        (the inverse of ``instantiate``). The façade used by the publish seam to
        turn a handler's returned model back into a payload.
        """
        if isinstance(value, dict):
            return cast("ModelData", value)
        engine = engine or cls._default_engine
        return engine.adapter.dump(value)

    @overload
    @classmethod
    def get_model(
        cls, key: ModelHandle, *, engine: Engine[VersionValue] | None = None
    ) -> Versionable[VersionValue]: ...
    @overload
    @classmethod
    def get_model(
        cls, key: ModelKey, *, engine: Engine[VersionValue] | None = None
    ) -> Versionable[VersionValue]: ...

    @singledispatchmethod
    @classmethod
    def get_model(
        cls: type[ManagerState[VersionValue]],
        key: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        """Return a registered model version; a bare class is looked up by class."""
        engine = engine or cls._default_engine
        return engine.get_model_by_class(key)

    @get_model.register(ModelKey)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return engine.get_model(
            engine.adapter.versionable(None, kind=key.kind, version=key.version)
        )

    @overload
    @classmethod
    def get_latest_model(
        cls,
        key: Comparable[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]: ...

    @overload
    @classmethod
    def get_latest_model(
        cls, key: ModelKind, *, engine: Engine[VersionValue] | None = None
    ) -> Versionable[VersionValue]: ...

    @singledispatchmethod
    @classmethod
    def get_latest_model(
        cls: type[ManagerState[VersionValue]],
        key: Comparable[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return engine.get_model(key)

    @get_latest_model.register(ModelKind)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelKind,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return engine.get_latest_model(key)

    @overload
    @classmethod
    def get_earliest_model(
        cls,
        key: Comparable[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]: ...
    @overload
    @classmethod
    def get_earliest_model(
        cls, key: ModelKind, *, engine: Engine[VersionValue] | None = None
    ) -> Versionable[VersionValue]: ...

    @singledispatchmethod
    @classmethod
    def get_earliest_model(
        cls: type[ManagerState[VersionValue]],
        key: Comparable[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return engine.get_model(key)

    @get_earliest_model.register(ModelKind)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelKind,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return engine.get_earliest_model(key)

    @classmethod
    def get(
        cls: type[ManagerState[VersionValue]],
        kind: ModelKind,
        version: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        """Return the registered versionable for ``kind``@``version``."""
        engine = engine or cls._default_engine
        key = ModelKey(kind, cast(VersionValue, engine.adapter.of(version)))
        return cls.get_model(key, engine=engine)
