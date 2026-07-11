"""Model registry — single source of truth for models, migrations, and hooks."""

import bisect
from collections import defaultdict
from functools import lru_cache
from itertools import chain, pairwise
from typing import ClassVar, Generic, Self, cast

import pendulum
from pydantic import BaseModel
from semver.version import Version

from pydantic_migrator.migration.versioning import VersionSentinel

from .exceptions import (
    MigrationError,
    MigrationNotFoundError,
    ModelAlreadyRegisteredError,
    ModelNotFoundError,
    RegistryError,
)
from .models import MigrationQuery, ModelQuery
from .types import (
    LookupKey,
    MigrationFunc,
    MigrationHookMap,
    MigrationHookProtocol,
    MigrationMap,
    VersionedModelProtocol,
    VersionValue,
    VModel,
)


class Registry(Generic[VersionValue]):
    """Ordered storage for versioned models, migrations, and hooks."""

    MIN_PREDICATES: ClassVar[int] = 2

    def __init__(self: Self, *, name: str | None = None) -> None:
        """Create a named registry.

        Internally maintains two lookup indexes:
        - ``_by_versions``: sorted list for O(log n) version-keyed bisect lookups.
        - ``_by_models``: inverted dict for O(1) model-class-keyed lookups.
        """
        self._name = name or "registry"
        self._by_versions: list[VersionedModelProtocol] = []
        self._by_models: dict[type[BaseModel], VersionedModelProtocol] = {}
        self._backward_compatible: list[VersionedModelProtocol] = []
        self._migrations: MigrationMap = {}
        self._hooks: MigrationHookMap = defaultdict(list)

    def __contains__(self, index: LookupKey) -> bool:
        """Check whether a version, model, or migration path is registered.

        ``v in registry``
            *v* is a :class:`VersionValue` — checks model by version existence.
        ``M in registry``
            *M* is a :class:`pydantic.BaseModel` subclass — checks model by model existence.
        ``v1:v2 in registry``
            Slice of version values or model classes — checks migration path existence.

        Returns:
            ``True`` if the lookup resolves to a registered entry.
        """  # noqa: E501

        if isinstance(index, Version) or isinstance(index, pendulum.Date):
            query = ModelQuery[VersionValue](version_value=cast(VersionValue, index))
        elif isinstance(index, slice):
            if isinstance(index.start, Version) or isinstance(index, pendulum.Date):
                query = MigrationQuery[VersionValue](
                    version_range=(index.start, index.stop)
                )
            elif isinstance(index.start, BaseModel):
                query = MigrationQuery[VersionValue](
                    version_range=(index.start, index.stop)
                )
            else:
                raise RegistryError(
                    self._name, f"Unsupported index type: {type(index)}"
                )
        elif issubclass(index, BaseModel):
            query = ModelQuery[VersionValue](model_cls=cast(type[BaseModel], index))
        else:
            raise RegistryError(self._name, "Unsupported index type: {type(index)}")

        if isinstance(query, ModelQuery):
            try:
                return self.get_model(query) is not None
            except ModelNotFoundError:
                return False
        elif isinstance(query, MigrationQuery):
            try:
                return self.get_migration(query) is not None
            except MigrationNotFoundError:
                return False
        raise RegistryError(self._name, f"Unsupported query type: {type(query)}")

    def __len__(self) -> int:
        return len(self._by_versions)

    def __getitem__(
        self, index: LookupKey
    ) -> VersionedModelProtocol[VersionValue, VModel] | MigrationFunc:
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
        if isinstance(index, type):
            if isinstance(index, Version) or isinstance(index, pendulum.Date):
                query = ModelQuery[VersionValue](
                    version_value=cast(VersionValue, index)
                )
            elif issubclass(index, BaseModel):
                query = ModelQuery[VersionValue](model_cls=cast(type[BaseModel], index))
            else:
                raise RegistryError(self._name, "Unsupported index type: {type(index)}")
            return self.get_model(query)
        elif isinstance(index, slice):
            if isinstance(index.start, Version) or isinstance(index, pendulum.Date):
                query = MigrationQuery[VersionValue](
                    version_range=(index.start, index.stop)  # type: ignore[arg-type]
                )
            elif issubclass(index.start, BaseModel):
                query = MigrationQuery[VersionValue](
                    version_range=(index.start, index.stop)  # type: ignore[arg-type]
                )
            else:
                raise RegistryError(
                    self._name, f"Unsupported index type: {type(index)}"
                )
            return cast(MigrationFunc, self.get_migration(query))
        raise RegistryError(self._name, f"Unsupported index type: {type(index)}")

    @property
    def versions(self: Self) -> list[VersionedModelProtocol]:
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
    def latest(self: Self) -> VersionedModelProtocol:
        """Most recent (highest) registered version.

        Returns:
            The last entry in the sorted versions list.

        Raises:
            ValueError: If no versions are registered.
        """
        if not self._by_versions:
            raise RegistryError(self._name, "No versions registered")
        return self._by_versions[-1]

    @lru_cache
    def is_backward_compatible(self: Self, query: ModelQuery[VersionValue]) -> bool:
        """True if *version* is marked as backward-compatible."""
        predicate = query.predicate
        if predicate is None:
            raise RegistryError(self._name, "No lookup predicate is defined")

        sentinel = VersionSentinel[VersionValue](cast(VersionValue, predicate))
        idx = bisect.bisect_left(self._backward_compatible, sentinel)
        return (
            idx < len(self._backward_compatible)
            and self._backward_compatible[idx] == sentinel
        )

    def copy(self: Self, name: str | None = None) -> "Registry[VersionValue]":
        """Return an independent shallow copy."""
        new = Registry(name=name)
        new._by_versions = list(self._by_versions)
        new._backward_compatible = list(self._backward_compatible)
        new._migrations = dict(self._migrations)
        new._hooks = defaultdict(list, {k: list(v) for k, v in self._hooks.items()})
        return new

    def store_model(
        self: Self,
        version: VersionedModelProtocol[VersionValue, VModel],
        backward_compatible: bool = False,
    ) -> VersionedModelProtocol:
        """Register a model class at *version*.

        Raises ValueError if (version, cls) is already registered.
        """
        if version in self._by_versions:
            raise ModelAlreadyRegisteredError(
                registry_name=self._name,
                version=version.version,
            )
        bisect.insort_left(self._by_versions, version)
        self._by_models[version.model] = version
        if backward_compatible:
            bisect.insort_left(self._backward_compatible, version)
        return version

    def get_model(
        self: Self, query: ModelQuery[VersionValue]
    ) -> VersionedModelProtocol:
        """Return the model class for *version* (default: latest)."""
        predicate = query.predicate
        if predicate is None and query.use_latest:
            return self.latest
        if isinstance(predicate, Version) or isinstance(predicate, pendulum.Date):
            sentinel = VersionSentinel[VersionValue](cast(VersionValue, predicate))
            idx = bisect.bisect_left(self._by_versions, sentinel)
            if idx < len(self._by_versions) and self._by_versions[idx] == sentinel:
                return self._by_versions[idx]
        elif issubclass(predicate, BaseModel):
            if predicate in self._by_models:
                return self._by_models[predicate]
        raise ModelNotFoundError(self._name, predicate)

    def remove_model(
        self: Self, version: VersionedModelProtocol[VersionValue, VModel]
    ) -> None:
        """Remove a model version and clean up related migrations and flags."""
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
        del self._by_versions[idx]
        del self._by_models[version.model]
        if version in self._backward_compatible:
            bc_idx = bisect.bisect_left(self._backward_compatible, version)
            del self._backward_compatible[bc_idx]

    def clear_models(self: Self) -> None:
        """Remove all models from the registry."""
        if not self._migrations:
            raise RegistryError(self._name, "Clear migrations first")
        self._by_versions.clear()
        self._by_models.clear()
        self._backward_compatible.clear()

    def store_migration(
        self: Self,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol,
        func: MigrationFunc,
    ) -> MigrationFunc:
        """Register a migration function between two versions.

        Migrations between non-adjacent versions are allowed only when all
        intermediate versions are backward-compatible.
        """
        if from_version not in self._by_versions or to_version not in self._by_versions:
            raise RegistryError(
                self._name,
                f"Versions {from_version} and {to_version} must be registered",
            )
        start = bisect.bisect_left(self._by_versions, from_version)
        stop = bisect.bisect_left(self._by_versions, to_version)
        if start != stop - 1:
            intermediate = self._by_versions[start + 1 : stop]
            backward_compatible_query = all(
                self.is_backward_compatible(
                    ModelQuery[VersionValue](version_value=v.version)
                )
                for v in intermediate
            )
            if not backward_compatible_query:
                raise RegistryError(
                    self._name,
                    f"Versions {from_version} and {to_version} are not adjacent "
                    "and intermediate versions are not all backward-compatible",
                )
        if (from_version, to_version) in self._migrations:
            raise RegistryError(
                self._name,
                f"Migration from {from_version} to {to_version} is already registered",
            )

        self._migrations[(from_version, to_version)] = func
        return func

    def get_migration(
        self,
        query: MigrationQuery,
    ) -> MigrationFunc | list[MigrationFunc]:
        """Return migration function(s) matching *query*.

        A single ``(from, to)`` pair returns a ``MigrationFunc``.
        Multiple pairs return a ``list[MigrationFunc]``.
        If *query.use_latest* is True and only one value is given,
        the latest registered version is used as the target.
        """
        predicates = list(query.predicate)
        if not predicates:
            raise ValueError("At least one version or model required")

        if query.use_latest and len(predicates) == 1:
            predicates.append(self.latest.version)

        if len(predicates) < self.MIN_PREDICATES:
            raise ValueError(
                "At least two values required (or one with use_latest=True)"
            )

        results: list[MigrationFunc] = []
        for from_raw, to_raw in pairwise(predicates):
            from_v = self._resolve_predicate(from_raw, query)
            to_v = self._resolve_predicate(to_raw, query)
            key = (from_v, to_v)
            if key not in self._migrations:
                raise MigrationError(
                    self._name, str(from_v), str(to_v), "No migration found"
                )
            results.append(self._migrations[key])

        return results[0] if len(results) == 1 else results

    def _resolve_predicate(
        self,
        raw: VersionValue | type[BaseModel],
        query: MigrationQuery,
    ) -> VersionedModelProtocol:
        """Resolve a raw predicate to a registered ``VersionedModelProtocol``."""
        if isinstance(raw, type):
            return self._by_models[raw]
        sentinel = VersionSentinel(raw)
        idx = bisect.bisect_left(self._by_versions, sentinel)
        return self._by_versions[idx]

    def remove_migration(
        self: Self,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol | None = None,
    ) -> None:
        """Remove migration(s).

        ``remove_migration(v1, v2)`` → single migration.
        ``remove_migration(v1:v3)`` → all migrations in the range [v1, v3).
        """

        if to_version is None:
            to_version = self.latest
        key = (from_version, to_version)

        if key in self._hooks:
            raise ValueError(f"Cannot remove migration {key}. Remove hooks first.")

        if key not in self._migrations:
            if not bool(self.find_migration_path(from_version, to_version)):
                raise MigrationError(
                    self._name,
                    from_version,
                    to_version,
                    "No migration found",
                )
        del self._migrations[key]

    def _remove_migration_range(
        self: Self,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol,
    ) -> None:
        lo = bisect.bisect_left(self._by_versions, from_version)
        hi = bisect.bisect_left(self._by_versions, to_version)
        for i in range(lo, hi):
            key = (self._by_versions[i], self._by_versions[i + 1])
            if key in self._hooks:
                raise ValueError(f"Cannot remove migration {key}. Remove hooks first.")
            if key in self._migrations:
                del self._migrations[key]

    def clear_migrations(self: Self) -> None:
        """Remove all migrations from the registry."""
        self.clear_hooks()
        self._migrations.clear()

    def find_migration_path(
        self: Self,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol,
    ) -> list[tuple[VersionedModelProtocol, VersionedModelProtocol]]:
        """Check whether a complete migration chain exists between two versions."""
        if from_version not in self._by_versions:
            raise ModelNotFoundError(self._name, from_version)
        if to_version not in self._by_versions:
            raise ModelNotFoundError(self._name, to_version)

        lo = bisect.bisect_left(self._by_versions, from_version)
        hi = bisect.bisect_left(self._by_versions, to_version)
        if lo >= hi:
            raise MigrationError(
                self._name,
                from_version,
                to_version,
                "Left version must be older than right version",
            )
        path = []
        current = from_version
        while lo < hi:
            nxt = self._by_versions[lo + 1]
            if (current, nxt) in self._migrations:
                path.append((current, nxt))
                current = nxt
                lo += 1
            elif self.is_backward_compatible(current):
                current = self.versions[
                    bisect.bisect_left(self._by_versions, current) + 1
                ]
                lo += 1
            else:
                raise MigrationError(
                    self._name,
                    current,
                    nxt,
                    f"No migration key is found ({current}, {nxt})",
                )
        return path

    def add_hook(
        self: Self,
        hook: MigrationHookProtocol,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol,
    ) -> None:
        """Register a hook for a migration step.

        Args:
            hook: The hook instance to register.
            from_version: Source version of the migration step.
            to_version: Target version of the migration step.
        """
        self._hooks[(from_version, to_version)].append(hook)

    def get_hook(
        self: Self,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol,
    ) -> list[MigrationHookProtocol]:
        """Return hooks registered for a migration step.

        Args:
            from_version: Source version of the migration step.
            to_version: Target version of the migration step.

        Returns:
            List of hooks for ``(from_version, to_version)``, or an empty
            list if none are registered.
        """
        return self._hooks.get((from_version, to_version), [])

    def remove_hook(
        self: Self,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol,
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
        key = (from_version, to_version)
        if hook is None:
            del self._hooks[key]
        elif hook in self._hooks[key]:
            self._hooks[key].remove(hook)
        else:
            raise ValueError(f"Hook {hook!r} is not registered for migration {key}")

    def clear_hooks(
        self: Self,
        from_version: VersionedModelProtocol | None = None,
        to_version: VersionedModelProtocol | None = None,
    ) -> None:
        """Clear hooks from the registry.

        Args:
            from_version: If given, scope clearing to this source version.
                If ``None``, clears all hooks globally.
            to_version: Target version. Required when *from_version* is given.
                If ``None``, defaults to the latest registered version.
        """
        if from_version is None:
            self._hooks.clear()
        else:
            if to_version is None:
                to_version = self.latest
            key = (from_version, to_version)
            if key in self._hooks:
                del self._hooks[key]
