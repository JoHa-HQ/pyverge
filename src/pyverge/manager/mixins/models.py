"""Model registration and lookup slice of the composed manager."""

from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, cast, overload

from pyverge.types import (
    Comparable,
    ModelBase,
    ModelKey,
    ModelKind,
    Versionable,
    VersionValue,
    VModel,
)

if TYPE_CHECKING:
    from pyverge.migration.engine import Engine

    from . import ManagerState


class ModelStoreMixin(Generic[VersionValue]):
    """Store and look up registered model versions."""

    @classmethod
    def store_model(
        cls: type[ManagerState[VersionValue]],
        key: type[VModel],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue, VModel]:
        """Register a model version through the engine."""
        engine = engine or cls._default_engine
        return engine.store_model(engine.adapter.versionable(key))

    @classmethod
    def list_versions(
        cls: type[ManagerState[VersionValue]],
        kind: ModelKind | None = None,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> list[Versionable[VersionValue, VModel]]:
        """Return registered versions, optionally filtered by *kind*."""
        engine = engine or cls._default_engine
        if kind is None:
            return engine.registry.versions
        return engine.registry.kind_versions(kind)

    @overload
    @classmethod
    def get_model(
        cls, key: type[VModel], *, engine: Engine[VersionValue] | None = None
    ) -> Versionable[VersionValue, VModel]: ...
    @overload
    @classmethod
    def get_model(
        cls, key: ModelKey, *, engine: Engine[VersionValue] | None = None
    ) -> Versionable[VersionValue, ModelBase]: ...

    @singledispatchmethod
    @classmethod
    def get_model(
        cls: type[ManagerState[VersionValue]],
        key: type[VModel],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue, VModel]:
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
    ) -> Versionable[VersionValue, ModelBase]:
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
    ) -> Versionable[VersionValue, ModelBase]: ...

    @overload
    @classmethod
    def get_latest_model(
        cls, key: ModelKind, *, engine: Engine[VersionValue] | None = None
    ) -> Versionable[VersionValue, ModelBase]: ...

    @singledispatchmethod
    @classmethod
    def get_latest_model(
        cls: type[ManagerState[VersionValue]],
        key: Comparable[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue, ModelBase]:
        engine = engine or cls._default_engine
        return engine.get_model(key)

    @get_latest_model.register(ModelKind)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelKind,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue, ModelBase]:
        engine = engine or cls._default_engine
        return engine.get_latest_model(key)

    @overload
    @classmethod
    def get_earliest_model(
        cls,
        key: Comparable[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue, ModelBase]: ...
    @overload
    @classmethod
    def get_earliest_model(
        cls, key: ModelKind, *, engine: Engine[VersionValue] | None = None
    ) -> Versionable[VersionValue, ModelBase]: ...

    @singledispatchmethod
    @classmethod
    def get_earliest_model(
        cls: type[ManagerState[VersionValue]],
        key: Comparable[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue, ModelBase]:
        engine = engine or cls._default_engine
        return engine.get_model(key)

    @get_earliest_model.register(ModelKind)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelKind,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue, ModelBase]:
        engine = engine or cls._default_engine
        return engine.get_earliest_model(key)

    @classmethod
    def get(
        cls: type[ManagerState[VersionValue]],
        kind: ModelKind,
        version: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue, VModel]:
        """Return the registered versionable for ``kind``@``version``."""
        engine = engine or cls._default_engine
        key = ModelKey(kind, cast(VersionValue, engine.adapter.of(version)))
        return cls.get_model(key, engine=engine)
