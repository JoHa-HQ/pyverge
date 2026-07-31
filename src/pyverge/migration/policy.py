"""Target policy compilation for migration graphs.

The migration engine is deliberately agnostic about *what* target version each
payload entry should converge to. This module turns a declarative policy (e.g.
"latest", "earliest", an explicit version, or per-kind overrides) into a
lightweight :class:`TargetResolver` that :class:`GraphBuilder` and the
individual :class:`EntryMigration` strategies consume.
"""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel

from .exceptions import ModelNotFoundError, RegistryError
from .registry import Registry
from .types import (
    ModelKind,
    TargetPolicy,
    TargetResolver,
    TargetSpec,
    Versionable,
    VersionValue,
    VModel,
)
from .versioning import SentinelNode


def compile_target_resolver(
    registry: Registry[VersionValue],
    policy: TargetPolicy | None,
    *,
    version_property: str = "version",
) -> TargetResolver:
    """Build a :class:`TargetResolver` from a declarative policy.

    The returned resolver accepts ``(kind, current)`` and returns the target
    versionable the graph should migrate to, or ``None`` if the entry should be
    skipped.

    Policy forms:
        * ``None`` or ``"skip"`` → skip every entry.
        * ``"latest"`` / ``"earliest"`` → registry extreme for the kind.
        * ``type[BaseModel]`` → resolve via registry to a versionable.
        * :class:`Versionable` → use as-is.
        * ``dict`` → per-kind override. The special key ``"*"`` is the
          fallback for kinds not explicitly listed.

    Args:
        registry: Source of registered versions and models.
        policy: Declarative target policy.
        version_property: Field name used to look up model versions.

    Returns:
        A callable matching :class:`TargetResolver`.
    """
    if isinstance(policy, dict):
        resolvers: dict[
            ModelKind | Literal["*"],
            TargetResolver,
        ] = {
            kind: _compile_spec(registry, spec, version_property=version_property)
            for kind, spec in policy.items()
        }
        fallback = resolvers.pop("*", None)

        def resolve(
            kind: ModelKind,
            current: Versionable[VersionValue, VModel],
        ) -> Versionable[VersionValue, VModel] | None:
            resolver = resolvers.get(kind, fallback)
            if resolver is None:
                return None
            return resolver(kind, current)

        return resolve

    return _compile_spec(registry, policy, version_property=version_property)


def _compile_spec(
    registry: Registry[VersionValue],
    spec: TargetSpec,
    *,
    version_property: str,
) -> TargetResolver:
    """Compile a single target spec into a resolver closure."""
    if spec is None:
        return _skip_resolver

    # Resolve string values first so we never compare a VersionNode/SentinelNode
    # to a string (their ``__eq__`` intentionally raises for mixed types).
    if isinstance(spec, str):
        if spec == "skip":
            return _skip_resolver
        if spec == "latest":
            return _latest_resolver(registry)
        if spec == "earliest":
            return _earliest_resolver(registry)
        raise RegistryError(
            registry.name,
            f"Unsupported target strategy: {spec!r}",
        )

    if isinstance(spec, type) and issubclass(spec, BaseModel):
        return _model_resolver(registry, spec, version_property=version_property)

    # Treat any remaining value as an explicit versionable target.  This avoids
    # an ``isinstance(spec, Versionable)`` protocol check that would trigger the
    # strict ``__eq__`` semantics of :class:`VersionNode` / :class:`SentinelNode`.
    return _versionable_resolver(spec)


def _skip_resolver(
    _kind: ModelKind,
    _current: Versionable[VersionValue, VModel],
) -> Versionable[VersionValue, VModel] | None:
    return None


def _latest_resolver(
    registry: Registry[VersionValue],
) -> TargetResolver:
    def resolve(
        kind: ModelKind,
        _current: Versionable[VersionValue, VModel],
    ) -> Versionable[VersionValue, VModel] | None:
        return registry.latest(kind)

    return resolve


def _earliest_resolver(
    registry: Registry[VersionValue],
) -> TargetResolver:
    def resolve(
        kind: ModelKind,
        _current: Versionable[VersionValue, VModel],
    ) -> Versionable[VersionValue, VModel] | None:
        return registry.earliest(kind)

    return resolve


def _model_resolver(
    registry: Registry[VersionValue],
    model_cls: type[BaseModel],
    *,
    version_property: str,
) -> TargetResolver:
    try:
        target = registry.get_model_by_class(model_cls)
    except ModelNotFoundError as exc:
        raise RegistryError(
            registry.name,
            f"Target model {model_cls.__name__} is not registered",
        ) from exc

    def resolve(
        kind: ModelKind,
        _current: Versionable[VersionValue, VModel],
    ) -> Versionable[VersionValue, VModel] | None:
        if kind != target.kind:
            raise RegistryError(
                registry.name,
                f"Target model {model_cls.__name__} belongs to kind "
                f"{target.kind!r}, but entry kind is {kind!r}",
            )
        return target

    return resolve


def _versionable_resolver(
    target: Versionable[VersionValue, VModel],
) -> TargetResolver:
    def resolve(
        kind: ModelKind,
        _current: Versionable[VersionValue, VModel],
    ) -> Versionable[VersionValue, VModel] | None:
        if kind != target.kind:
            raise RegistryError(
                "target",
                f"Target {target} belongs to kind {target.kind!r}, "
                f"but entry kind is {kind!r}",
            )
        return target

    return resolve


def _string_resolver(
    registry: Registry[VersionValue],
    value: str,
    *,
    version_property: str,
) -> TargetResolver:
    """Resolve a raw string as either a kind or a version value."""

    # First try to interpret the string as a version value for the current kind.
    def resolve(
        kind: ModelKind,
        _current: Versionable[VersionValue, VModel],
    ) -> Versionable[VersionValue, VModel] | None:
        strategy = _current.strategy
        try:
            parsed = strategy(value)
            sentinel: Versionable[VersionValue, VModel] = cast(
                Versionable[VersionValue, VModel],
                SentinelNode(kind, parsed),
            )
            return registry.get_model(sentinel)
        except (TypeError, ValueError):
            pass

        # If that fails, try finding a kind whose literal name matches.
        if kind == value:
            raise RegistryError(
                registry.name,
                f"String target {value!r} matched a kind, not a version",
            )
        raise RegistryError(
            registry.name,
            f"Could not resolve string target {value!r} to a version",
        )

    return resolve
