from __future__ import annotations

from typing import Any, Generic, TypeVar

from .adapters import ModelAdapter, PydanticModelAdapter
from .engine import Engine
from .models import MigrationSettings
from .registry import Registry
from .strategy import DefaultEntryMigration
from .types import Executor, VersionValue

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


class ModelManager(metaclass=_ModelManagerClass):
    """Legacy convenience wrapper retained for backward compatibility."""

    def __init__(
        self,
        adapter: ModelAdapter | None = None,
        engine: Engine[VersionValue] | None = None,
        executor: Executor | None = None,
        registry: Registry[Any] | None = None,
        settings: MigrationSettings | None = None,
    ) -> None:
        self._settings = settings or MigrationSettings()
        self._adapter = adapter or PydanticModelAdapter(
            version_property=self._settings.version_property,
            kind_property=self._settings.kind_property,
        )
        self._registry = registry or Registry[Any]()
        self._engine = engine
        self._entry_migration = DefaultEntryMigration()

    @property
    def engine(self) -> Engine[VersionValue] | None:
        """Return the configured engine, if any."""
        return self._engine

    @property
    def registry(self) -> Registry[Any]:
        """Return the underlying registry."""
        return self._registry

    def model(self, kind: str, version: str | Any) -> Any:
        """Decorator placeholder to register a model version."""
        raise NotImplementedError("ModelManager.model decorator is not yet implemented")

    def migration(
        self, kind: str, source: str | Any, target: str | Any
    ) -> Any:
        """Decorator placeholder to register a migration."""
        raise NotImplementedError(
            "ModelManager.migration decorator is not yet implemented"
        )

    def migrate(
        self,
        payload: dict[str, Any],
        target: Any | None = None,
        direction: str = "any",
        on_direction_violation: str = "skip",
        on_missing_path: str = "raise",
    ) -> dict[str, Any]:
        """Migrate a payload using the configured engine."""
        if self._engine is None:
            raise RuntimeError("ModelManager has no engine configured")
        return self._engine.migrate(
            payload,
            target=target,
            direction=direction,
            on_direction_violation=on_direction_violation,
            on_missing_path=on_missing_path,
        )

    def info(self) -> dict[str, Any]:
        """Return manager metadata."""
        return {
            "adapter": type(self._adapter).__name__,
            "registry": {
                "name": self._registry.name,
                "models": len(self._registry.versions),
                "migrations": len(list(self._registry.migrations())),
            },
        }
