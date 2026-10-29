from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, cast

from pyverge.core.types import (
    ModelData,
    ModelKey,
    ModelKind,
    VersionValue,
)
from pyverge.discovery import ModelRegistrationMode, RegisterModel
from pyverge.schemas.types import (
    ModelHandle,
)
from pyverge.versioning import Comparable, NodeId, Versionable, VersionNode

from ..descriptors import hybridmethod

if TYPE_CHECKING:
    from pyverge.engine import Engine
    from pyverge.manager.manager import Manager


class ModelStoreMixin(Generic[VersionValue]):
    """Store and look up registered model versions."""

    @hybridmethod
    @singledispatchmethod
    @classmethod
    def store_model(
        cls: type[Manager[VersionValue]],
        key: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return cast(
            Versionable[VersionValue],
            engine.register(RegisterModel(key, ModelRegistrationMode.STRICT)),
        )

    @store_model.register(VersionNode)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        version: VersionNode[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return cast(
            Versionable[VersionValue],
            engine.register(RegisterModel(version, ModelRegistrationMode.STRICT)),
        )

    @hybridmethod
    @singledispatchmethod
    @classmethod
    def reconcile_model(
        cls: type[Manager[VersionValue]],
        key: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return cast(
            Versionable[VersionValue],
            engine.register(RegisterModel(key, ModelRegistrationMode.RECONCILE)),
        )

    @reconcile_model.register(VersionNode)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        version: VersionNode[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]:
        engine = engine or cls._default_engine
        return cast(
            Versionable[VersionValue],
            engine.register(RegisterModel(version, ModelRegistrationMode.RECONCILE)),
        )

    def missing_references(
        self: Manager[VersionValue],
        version: Versionable[VersionValue],
    ) -> frozenset[NodeId]:
        return self.engine.registry.missing_references(version)

    def validate_graph(
        self: Manager[VersionValue],
        version: Versionable[VersionValue] | None = None,
    ) -> None:
        self.engine.validate(version)

    @hybridmethod
    @classmethod
    def list_versions(
        cls: type[Manager[VersionValue]],
        kind: ModelKind | None = None,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> list[VersionNode[VersionValue]]:
        engine = engine or cls._default_engine
        if kind is None:
            return engine.registry.versions
        return engine.registry.kind_versions(kind)

    @hybridmethod
    @classmethod
    def get_entities(
        cls: type[Manager[VersionValue]],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> list[ModelKind]:
        engine = engine or cls._default_engine
        return engine.get_entities()

    @hybridmethod
    @classmethod
    def identifies(
        cls: type[Manager[VersionValue]],
        key: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> bool:
        engine = engine or cls._default_engine
        return engine.adapter.identify(key)

    @hybridmethod
    @classmethod
    def dump(
        cls: type[Manager[VersionValue]],
        value: object,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> ModelData:
        if isinstance(value, dict):
            return cast("ModelData", value)
        engine = engine or cls._default_engine
        return engine.adapter.dump(value)

    @hybridmethod
    @classmethod
    def get_model(
        cls: type[Manager[VersionValue]],
        key: ModelHandle | ModelKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionNode[VersionValue]:
        engine = engine or cls._default_engine
        if isinstance(key, ModelKey):
            return engine.get_model(
                engine.adapter.version_key(
                    kind=key.kind,
                    version=key.version,
                )
            )
        return engine.get_model_by_class(key)

    @hybridmethod
    @classmethod
    def get_latest_model(
        cls: type[Manager[VersionValue]],
        key: Comparable[VersionValue] | ModelKind,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionNode[VersionValue]:
        engine = engine or cls._default_engine
        if isinstance(key, str):
            return engine.get_latest_model(key)
        return engine.get_model(key)

    @hybridmethod
    @classmethod
    def get_earliest_model(
        cls: type[Manager[VersionValue]],
        key: Comparable[VersionValue] | ModelKind,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionNode[VersionValue]:
        engine = engine or cls._default_engine
        if isinstance(key, str):
            return engine.get_earliest_model(key)
        return engine.get_model(key)

    @hybridmethod
    @classmethod
    def get(
        cls: type[Manager[VersionValue]],
        kind: ModelKind,
        version: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionNode[VersionValue]:
        engine = engine or cls._default_engine
        key = ModelKey(kind, cast(VersionValue, engine.adapter.of(version)))
        return cls.get_model(key, engine=engine)
