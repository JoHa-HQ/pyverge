"""Compatibility shim for the legacy ModelManager API."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from .adapters import ModelAdapter, PydanticModelAdapter
from .engine import Engine
from .executor import SequentialExecutor
from .graph import GraphBuilder
from .models import DiscoverySettings, MigrationSettings
from .registry import Registry
from .strategy import DefaultEntryMigration, EntryMigration
from .types import Executor, VersionValue
from .walker import CompoundKeyWalker

_T = TypeVar("_T")


class _ModelManagerClass(type, Generic[_T]):
    """Metaclass that supports ``ModelManager[Container, Settings()]`` syntax."""

    def __class_getitem__(cls, params: Any) -> type[ModelManager]:
        if isinstance(params, tuple):
            _, settings = params
        else:
            settings = params
        return cls._subclass(settings)

    def _subclass(cls, settings: MigrationSettings) -> type[ModelManager]:
        class _ConfiguredManager(ModelManager):
            def __init__(
                self,
                executor: Executor | None = None,
                registry: Registry[Any] | None = None,
            ) -> None:
                super().__init__(
                    executor=executor,
                    registry=registry,
                    settings=settings,
                )

        _ConfiguredManager.__name__ = "ModelManager"
        _ConfiguredManager.__qualname__ = "ModelManager"
        return _ConfiguredManager


class ModelManager(Engine[VersionValue], metaclass=_ModelManagerClass):
    """Legacy convenience wrapper retained for backward compatibility."""

    def __init__(
        self,
        executor: Executor | None = None,
        settings: MigrationSettings | None = None,
        registry: Registry[Any] | None = None,
        graph_builder: GraphBuilder[Any] | None = None,
        adapter: ModelAdapter | None = None,
        entry_migration: EntryMigration[Any] | None = None,
    ) -> None:
        settings = settings or MigrationSettings()
        registry = registry or Registry()
        adapter = adapter or PydanticModelAdapter(
            version_property=settings.version_property,
            kind_property=settings.kind_property,
        )
        entry_migration = entry_migration or DefaultEntryMigration()
        super().__init__(
            registry=registry,
            settings=settings,
            executor=executor or SequentialExecutor(),
            graph_builder=graph_builder
            or GraphBuilder(
                registry,
                DiscoverySettings(
                    version_property=settings.version_property,
                    kind_property=settings.kind_property,
                ),
                CompoundKeyWalker(
                    registry,
                    settings=DiscoverySettings(
                        version_property=settings.version_property,
                        kind_property=settings.kind_property,
                    ),
                ),
            ),
            adapter=adapter,
            entry_migration=entry_migration,
        )
