"""Model registry — single source of truth for models, migrations, and hooks."""

import bisect
from collections import defaultdict
from functools import lru_cache
from itertools import chain
from typing import Generic, Self, cast

import pendulum
from pydantic import BaseModel
from semver.version import Version

from .exceptions import (
    MigrationAlreadyRegisteredError,
    MigrationNotFoundError,
    ModelAlreadyRegisteredError,
    ModelNotFoundError,
    RegistryError,
)
from .types import (
    LookupKey,
    MigrationFunc,
    MigrationHookMap,
    MigrationHookProtocol,
    MigrationKey,
    MigrationMap,
    ModelKind,
    ModelVersionKey,
    Versionable,
    VersionValue,
    VModel,
)
from .versioning import VersionSentinel


class Registry(Generic[VersionValue]):
    """Ordered storage for versioned models, migrations, and hooks."""

    def __init__(self: Self, *, name: str | None = None) -> None:
        """Create a named registry.

        Internally maintains two lookup indexes:
        - ``_by_versions``: sorted list for O(log n) version-keyed bisect lookups.
        - ``_by_models``: inverted dict for O(1) model-class-keyed lookups.
        - ``_by_kinds``: inverted dict for O(log n) kind-keyed lookups.
        """
        self._name = name or "registry"
        self._by_versions: list[Versionable] = []
        self._by_kinds: dict[ModelKind, list[Versionable]] = defaultdict(list)
        self._by_models: dict[type[BaseModel], Versionable] = {}
        self._backward_compatible: list[Versionable] = []
        self._migrations: MigrationMap = {}
        self._hooks: MigrationHookMap = defaultdict(list)

    def __contains__(self, index: LookupKey) -> bool:
        """Check whether a version, model, or migration path is registered.

        ``(kind, version) in registry``
            Compound key — checks exact model by kind + version.
        ``M in registry``
            *M* is a :class:`pydantic.BaseModel` subclass — checks model by class.
        ``(v1, v2) in registry``
            Pair of :class:`Versionable` objects — checks single migration.
        ``v1:v2 in registry``
            Slice of :class:`Versionable` objects — checks migration path.

        Returns:
            ``True`` if the lookup resolves to a registered entry.
        """

        # MigrationKey: (Versionable, Versionable)
        if isinstance(index, tuple) and isinstance(index[0], Versionable):
            return index in self._migrations

        # ModelVersionKey: (kind, version)
        elif isinstance(index, tuple) and isinstance(index[0], str):
            try:
                return self.get_model(cast(ModelVersionKey, index)) is not None
            except ModelNotFoundError:
                return False
        # Pydantic model
        elif isinstance(index, type) and issubclass(index, BaseModel):
            try:
                return self.get_model(cast(type[BaseModel], index)) is not None
            except ModelNotFoundError:
                return False
        raise RegistryError(self._name, f"Unsupported index type: {type(index)}")

    def __getitem__(
        self, index: LookupKey
    ) -> Versionable[VersionValue, VModel] | MigrationFunc:
        """Lookup by version, model class, or slice.

        ``registry[v]``
            *v* is a version value — returns the :class:`VersionedModelProtocol`.
        ``registry[M]``
            *M* is a :class:`pydantic.BaseModel` subclass — returns the
            :class:`VersionedModelProtocol` bound to that model.
        ``registry[v1:v2]``
            Slice of version values or model classes — returns the
            :class:`MigrationFunc` for that step.

        Returns:
            The resolved entry, or raises :class:`RegistryError` on unknown formats.
        """
        if isinstance(index, tuple) and isinstance(index[1], (Version, pendulum.Date)):
            return self.get_model(index)  # type: ignore[arg-type]
        elif isinstance(index, type) and issubclass(index, BaseModel):
            return self.get_model(cast(type[BaseModel], index))
        elif isinstance(index, tuple) and isinstance(index[0], Versionable):
            return self.get_migration(index)
        raise RegistryError(self._name, f"Unsupported index type: {type(index)}")

    @property
    def versions(self: Self) -> list[Versionable]:
        """Registered versions in ascending order.

        Returns:
            Sorted list of all registered ``VersionedModelProtocol`` entries.
        """
        return self._by_versions

    @property
    def models(self: Self) -> set[type[BaseModel]]:
        """Registered Pydantic model classes.

        Returns:
            Set of model classes keyed by version in ``_by_models``.
        """
        return set([v.model for v in self._by_models.values()])

    @property
    def migrations(
        self: Self,
    ) -> list[MigrationFunc]:
        """Registered migration functions.

        Returns:
            List of all stored migration callables.
        """
        return list(self._migrations.values())

    @property
    def hooks(
        self: Self,
    ) -> list[MigrationHookProtocol]:
        """Registered migration hooks.

        Returns:
            Flattened list of all hooks across all migration keys.
        """
        return list(chain(*self._hooks.values()))

    @property
    def latest_version(self) -> Versionable:
        """The most recently registered version overall."""
        if not self._by_versions:
            raise RegistryError(self._name, "No versions registered")
        return self._by_versions[-1]

    def latest(
        self: Self,
        kind: ModelKind,
    ) -> Versionable[VersionValue, VModel]:
        """Most recent (highest) registered version.

        Returns:
            The last entry in the sorted versions list.

        Raises:
            ValueError: If no versions are registered.
        """
        if kind not in self._by_kinds:
            raise RegistryError(self._name, "No versions registered")
        return self._by_kinds[kind][-1]

    @lru_cache(typed=True)
    def is_backward_compatible(
        self: Self,
        key: ModelVersionKey | type[BaseModel],
    ) -> bool:
        """True if *version* is marked as backward-compatible."""
        if isinstance(key, type) and issubclass(key, BaseModel):
            target = self._by_models.get(key)
        if isinstance(key, tuple) and isinstance(key[0], str):
            sentinel = VersionSentinel[VersionValue](key[0], key[1])
            idx = bisect.bisect_left(self._by_versions, sentinel)
            if idx < len(self._by_versions):
                target = self._by_versions[idx]
            else:
                target = None
        else:
            raise RegistryError(self._name, f"Invalid key: {key}")

        if target is None:
            raise ModelNotFoundError(self._name, key)

        idx = bisect.bisect_left(self._backward_compatible, target)
        return (
            idx < len(self._backward_compatible)
            and self._backward_compatible[idx] == target
        )

    def copy(self: Self, name: str | None = None) -> "Registry[VersionValue]":
        """Return an independent shallow copy."""
        new = Registry(name=name)
        new._by_versions = list(self._by_versions)
        new._by_kinds = dict(self._by_kinds)
        new._backward_compatible = list(self._backward_compatible)
        new._migrations = dict(self._migrations)
        new._hooks = defaultdict(list, {k: list(v) for k, v in self._hooks.items()})
        return new

    def store_model(
        self: Self,
        version: Versionable[VersionValue, VModel],
        backward_compatible: bool = False,
    ) -> Versionable:
        """Register a model class at *version*.

        Raises ValueError if (version, cls) is already registered.
        """
        if version in self._by_versions:
            raise ModelAlreadyRegisteredError(
                registry_name=self._name,
                version=version.version,
            )
        self._by_models[version.model] = version
        bisect.insort_left(self._by_versions, version)
        bisect.insort_left(self._by_kinds[version.version[0]], version)
        if backward_compatible:
            bisect.insort_left(self._backward_compatible, version)
        return version

    def _find_model(
        self: Self,
        key: (
            type[BaseModel]
            | Versionable[VersionValue, VModel]
            | VersionSentinel[VersionValue]
        ),
    ) -> Versionable | None:
        """Find a registered model by class, versioned model, or sentinel."""
        if isinstance(key, type) and issubclass(key, BaseModel):
            return self._by_models.get(key)
        if isinstance(key, (Versionable, VersionSentinel)):
            idx = bisect.bisect_left(self._by_versions, key)
            if (
                idx < len(self._by_versions)
                and (target := self._by_versions[idx]) == key
            ):
                return target
        return None

    def get_model(
        self: Self,
        key: ModelVersionKey | type[BaseModel],
    ) -> Versionable:
        """Return the model matching *key*, or raise :class:`ModelNotFoundError`.

        *key* may be a ``(kind, version)`` tuple or a
        :class:`pydantic.BaseModel` subclass.
        """
        if isinstance(key, type) and issubclass(key, BaseModel):
            model = self._by_models.get(key)
        elif isinstance(key, tuple) and isinstance(key[0], str):
            sentinel = VersionSentinel[VersionValue](key[0], key[1])
            idx = bisect.bisect_left(self._by_versions, sentinel)
            if idx < len(self._by_versions):
                model = self._by_versions[idx]
            else:
                model = None
        else:
            model = None

        if model is None:
            raise ModelNotFoundError(self._name, key)
        return model

    def remove_model(
        self: Self,
        key: ModelVersionKey,
    ) -> None:
        """Remove a model version and clean up related migrations and flags."""
        version = VersionSentinel[VersionValue](key[0], key[1])
        idx = bisect.bisect_left(self._by_versions, version)
        if idx == len(self._by_versions) or self._by_versions[idx] != version:
            raise RegistryError(self._name, f"Version {version} is not registered")

        # Check for dependent migrations
        affected = [(f, t) for (f, t) in self._migrations if version in (f, t)]
        if affected:
            pairs = ", ".join(f"{f}→{t}" for f, t in affected)
            raise RegistryError(
                self._name,
                f"Cannot remove version {version}: "
                f"it is referenced by migrations: {pairs}",
            )

        version = self._by_versions[idx]

        if version in self._backward_compatible:
            bc_idx = bisect.bisect_left(self._backward_compatible, version)
            del self._backward_compatible[bc_idx]

        del self._by_versions[idx]
        del self._by_models[version.model]

        idx = bisect.bisect_left(self._by_kinds[version.version[0]], version)
        del self._by_kinds[version.version[0]][idx]

    def clear_models(self: Self) -> None:
        """Remove all models from the registry."""
        if self._migrations:
            raise RegistryError(self._name, "Clear migrations first")
        self._by_versions.clear()
        self._by_models.clear()
        self._by_kinds.clear()
        self._backward_compatible.clear()

    def store_migration(
        self: Self,
        key: (
            tuple[ModelVersionKey, ModelVersionKey]
            | tuple[type[BaseModel], type[BaseModel]]
            | tuple[
                Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]
            ]
        ),
        func: MigrationFunc,
    ) -> MigrationFunc:
        """Register a migration function between two versions.

        *key* is a ``(from, to)`` pair where both elements are
        ``(kind, version)`` tuples **or** both are model classes.

        Migrations between non-adjacent versions are allowed only when all
        intermediate versions are backward-compatible.
        """
        if (isinstance(key[0], type) and issubclass(key[0], BaseModel)) or (
            isinstance(key[0], tuple) and issubclass(key[1], str)
        ):
            migration_key = cast(MigrationKey, self._resolve_migration_pair(key))
        else:
            migration_key = cast(MigrationKey, key)

        if any(v not in self._by_versions for v in migration_key):
            raise MigrationNotFoundError(self._name, migration_key)

        if migration_key in self._migrations:
            raise MigrationAlreadyRegisteredError(self._name, migration_key)

        self._migrations[migration_key] = func
        return func

    def get_migration(
        self,
        key: (
            tuple[ModelVersionKey, ModelVersionKey]
            | tuple[type[BaseModel], type[BaseModel]]
            | tuple[
                Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]
            ]
        ),
    ) -> MigrationFunc:
        """Return the migration for *key*, or raise :class:`MigrationError`.

        *key* is a ``(from, to)`` pair where both elements are
        ``(kind, version)`` tuples **or** both are model classes.
        """
        if not isinstance(key[0], Versionable):
            migration_key = cast(
                MigrationKey,
                tuple(self.get_model(part) for part in key),  # type: ignore[assignment]
            )
        else:
            migration_key = cast(MigrationKey, key)

        if migration_key not in self._migrations:
            raise MigrationNotFoundError(
                self._name,
                migration_key,
            )
        return self._migrations[migration_key]

    def remove_migration(
        self: Self,
        key: (
            tuple[ModelVersionKey, ModelVersionKey]
            | tuple[type[BaseModel], type[BaseModel]]
            | tuple[
                Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]
            ]
        ),
    ) -> None:
        """Remove migration(s).

        ``remove_migration(v1, v2)`` → single migration.
        ``remove_migration(v1:v3)`` → all migrations in the range [v1, v3).
        """

        if not isinstance(key[0], Versionable):
            migration_key = cast(
                MigrationKey,
                tuple(self.get_model(part) for part in key),  # type: ignore[assignment]
            )
        else:
            migration_key = cast(MigrationKey, key)

        if migration_key in self._hooks:
            raise MigrationNotFoundError(self._name, migration_key)

        del self._migrations[migration_key]

    def clear_migrations(self: Self) -> None:
        """Remove all migrations from the registry."""
        self.clear_hooks()
        self._migrations.clear()

    def add_hook(
        self: Self,
        key: (
            tuple[ModelVersionKey, ModelVersionKey]
            | tuple[type[BaseModel], type[BaseModel]]
            | tuple[
                Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]
            ]
        ),
        hook: MigrationHookProtocol,
    ) -> None:
        """Register a hook for a migration step.

        Args:
            key: The migration key to associate with the hook.
            hook: The hook instance to register.
            from_version: Source version of the migration step.
            to_version: Target version of the migration step.
        """

        if not isinstance(key[0], Versionable):
            migration_key = cast(
                MigrationKey,
                tuple(self.get_model(part) for part in key),  # type: ignore[assignment]
            )
        else:
            migration_key = cast(MigrationKey, key)

        if migration_key not in self._migrations:
            raise RegistryError(
                self._name, f"No migration found for key {migration_key}"
            )
        self._hooks[migration_key].append(hook)

    def get_hooks(
        self: Self,
        key: (
            tuple[ModelVersionKey, ModelVersionKey]
            | tuple[type[BaseModel], type[BaseModel]]
            | tuple[
                Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]
            ]
        ),
    ) -> list[MigrationHookProtocol]:
        """Return hooks registered for a migration step.

        Args:
            key: The migration key to retrieve hooks for.
            hook: Optional hook to filter by.

        Returns:
            List of hooks for ``key``, or an empty
            list if none are registered.
        """

        if not isinstance(key[0], Versionable):
            migration_key = cast(
                MigrationKey,
                tuple(self.get_model(part) for part in key),  # type: ignore[assignment]
            )
        else:
            migration_key = cast(MigrationKey, key)

        if migration_key not in self._hooks:
            raise RegistryError(self._name, f"No hooks registered for key {key}")
        return self._hooks[migration_key]

    def remove_hook(
        self: Self,
        key: (
            tuple[ModelVersionKey, ModelVersionKey]
            | tuple[type[BaseModel], type[BaseModel]]
            | tuple[
                Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]
            ]
        ),
        hook: MigrationHookProtocol | None = None,
    ) -> None:
        """Remove hooks for a migration step.

        Args:
            from_version: Source version of the migration step.
            to_version: Target version of the migration step.
            hook: A specific hook to remove. If ``None``, removes all hooks
                for the ``(from_version, to_version)`` key.

        Raises:
            ValueError: If *hook* is given but not registered for this key.
        """

        if not isinstance(key[0], Versionable):
            migration_key = cast(
                MigrationKey,
                tuple(self.get_model(part) for part in key),  # type: ignore[assignment]
            )
        else:
            migration_key = cast(MigrationKey, key)

        if migration_key not in self._hooks:
            raise RegistryError(
                self._name, f"No hooks registered for migration {migration_key}"
            )

        if hook is None:
            del self._hooks[migration_key]
        elif hook in self._hooks[migration_key]:
            self._hooks[migration_key].remove(hook)
        else:
            raise ValueError(f"Hook {hook!r} is not registered for migration {key}")

    def clear_hooks(
        self: Self,
        key: (
            tuple[ModelVersionKey, ModelVersionKey]
            | tuple[type[BaseModel], type[BaseModel]]
            | tuple[
                Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]
            ]
            | None
        ) = None,
    ) -> None:
        """Clear hooks from the registry.

        Args:
            key: If given, clear only hooks for this migration key.
            from_version: If given, scope clearing to this source version.
                If ``None``, clears all hooks globally.
            to_version: Target version. Required when *from_version* is given.
                If ``None``, defaults to the latest registered version.
        """

        if key is None:
            [hooks.clear() for hooks in self._hooks.values()]
            self._hooks.clear()

        if isinstance(key, tuple) and not isinstance(key[0], Versionable):
            migration_key = cast(
                MigrationKey,
                tuple(self.get_model(part) for part in key),  # type: ignore[assignment]
            )
        else:
            migration_key = cast(MigrationKey, key)

        if migration_key not in self._hooks:
            raise RegistryError(
                self._name, f"No hooks registered for migration {migration_key}"
            )

        self._hooks[migration_key].clear()
        del self._hooks[migration_key]
