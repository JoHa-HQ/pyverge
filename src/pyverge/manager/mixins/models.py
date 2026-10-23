from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, cast

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
    from pyverge.manager.manager import Manager
    from pyverge.migration.engine import Engine


class ModelStoreMixin(Generic[VersionValue]):
    """Store and look up registered model versions."""

    @singledispatchmethod
    @classmethod
    def store_model(
        cls: type[Manager[VersionValue]],
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
        cls: type[Manager[VersionValue]],
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
        cls: type[Manager[VersionValue]],
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
        cls: type[Manager[VersionValue]],
        version: VersionNode[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return engine.reconcile_model(version)

    def missing_references(
        self: Manager[VersionValue],
        version: Versionable[VersionValue],
    ) -> frozenset[ModelVersionKey]:
        """Return the versioned ``(kind, version)`` pairs *version* declares
        but that are not registered."""
        return self.engine.registry.missing_references(version)

    def validate_graph(
        self: Manager[VersionValue],
        version: Versionable[VersionValue] | None = None,
    ) -> None:
        """Validate registered models' declared references are registered.

        Raises :class:`~pyverge.core.MissingReferenceError` on the first model
        that references an unregistered versioned kind.
        """
        self.engine.validate(version)

    @classmethod
    def list_versions(
        cls: type[Manager[VersionValue]],
        kind: ModelKind | None = None,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> list[VersionNode[VersionValue]]:
        """Return registered versions, optionally filtered by *kind*."""
        engine = engine or cls._default_engine
        if kind is None:
            return engine.registry.versions
        return engine.registry.kind_versions(kind)

    @classmethod
    def get_entities(
        cls: type[Manager[VersionValue]],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> list[ModelKind]:
        """Return the kinds that have at least one registered version."""
        engine = engine or cls._default_engine
        return engine.get_entities()

    @classmethod
    def identifies(
        cls: type[Manager[VersionValue]],
        key: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> bool:
        """Return whether *key* is a versionable model this manager can handle."""
        engine = engine or cls._default_engine
        return engine.adapter.identify(key)

    @classmethod
    def dump(
        cls: type[Manager[VersionValue]],
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

    @classmethod
    def get_model(
        cls: type[Manager[VersionValue]],
        key: ModelHandle | ModelKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionNode[VersionValue]:
        """Return a registered model version by class or by key."""
        engine = engine or cls._default_engine
        if isinstance(key, ModelKey):
            return engine.get_model(
                engine.adapter.version_key(kind=key.kind, version=key.version)
            )
        return engine.get_model_by_class(key)

    @classmethod
    def get_latest_model(
        cls: type[Manager[VersionValue]],
        key: Comparable[VersionValue] | ModelKind,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionNode[VersionValue]:
        """Return the latest version for a kind or the given version identity."""
        engine = engine or cls._default_engine
        if isinstance(key, str):
            return engine.get_latest_model(key)
        return engine.get_model(key)

    @classmethod
    def get_earliest_model(
        cls: type[Manager[VersionValue]],
        key: Comparable[VersionValue] | ModelKind,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionNode[VersionValue]:
        """Return the earliest version for a kind or the given version identity."""
        engine = engine or cls._default_engine
        if isinstance(key, str):
            return engine.get_earliest_model(key)
        return engine.get_model(key)

    @classmethod
    def get(
        cls: type[Manager[VersionValue]],
        kind: ModelKind,
        version: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionNode[VersionValue]:
        """Return the registered versionable for ``kind``@``version``."""
        engine = engine or cls._default_engine
        key = ModelKey(kind, cast(VersionValue, engine.adapter.of(version)))
        return cls.get_model(key, engine=engine)
