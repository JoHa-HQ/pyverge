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
    ModelAdapter,
    ModelBase,
    ModelKind,
    TargetPolicy,
    TargetResolver,
    TargetSpec,
    Versionable,
    VersionValue,
    VersionValue_co,
    VModel_co,
)
from .versioning import SentinelNode


def compile_target_resolver(
    registry: Registry[VersionValue, ModelBase],
    policy: TargetPolicy | None,
    *,
    version_property: str = "version",
    adapter: ModelAdapter,
) -> TargetResolver:
    """Build a :class:`TargetResolver` from a declarative policy.

    The returned resolver accepts ``(kind, current)`` and returns the target
    versionable the graph should migrate to, or ``None`` if the entry should be
    skipped.

    Policy forms:
        * ``None`` or ``"skip"`` → skip every entry.
        * ``"latest"`` / ``"earliest"`` → registry extreme for the kind.
        * an explicit version string (e.g. ``"1.5.0"``) → the registered
          version for the entry's kind.
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
            kind: compile_target_spec(
                registry, spec, version_property=version_property, adapter=adapter
            )
            for kind, spec in policy.items()
        }
        fallback = resolvers.pop("*", None)

        def resolve(
            kind: ModelKind,
            current: Versionable[VersionValue_co, VModel_co],
        ) -> Versionable[VersionValue_co, VModel_co] | None:
            resolver = resolvers.get(kind, fallback)
            if resolver is None:
                return None
            return resolver(kind, current)

        return resolve

    return compile_target_spec(
        registry, policy, version_property=version_property, adapter=adapter
    )


def compile_target_spec(
    registry: Registry[VersionValue, ModelBase],
    spec: TargetSpec,
    *,
    version_property: str,
    adapter: ModelAdapter,
) -> TargetResolver:
    """Compile a single target spec into a resolver closure."""
    if spec is None:
        return _skip_resolver

    # Resolve string values first so we never compare a VersionNode/SentinelNode
    # to a string (their ``__eq__`` intentionally raises for mixed types).
    if isinstance(spec, str):
        if spec == "skip":
            resolver = _skip_resolver
        elif spec == "latest":
            resolver = _latest_resolver(registry)
        elif spec == "earliest":
            resolver = _earliest_resolver(registry)
        else:
            resolver = _string_resolver(registry, spec, adapter)
        return resolver

    if isinstance(spec, type) and issubclass(spec, BaseModel):
        return _model_resolver(registry, spec, version_property=version_property)

    # Treat any remaining value as an explicit versionable target.  This avoids
    # an ``isinstance(spec, Versionable)`` protocol check that would trigger the
    # strict ``__eq__`` semantics of :class:`VersionNode` / :class:`SentinelNode`.
    return _versionable_resolver(spec)


def _skip_resolver(
    _kind: ModelKind,
    _current: Versionable[VersionValue_co, VModel_co],
) -> Versionable[VersionValue_co, VModel_co] | None:
    return None


def _latest_resolver(
    registry: Registry[VersionValue, ModelBase],
) -> TargetResolver:
    def resolve(
        kind: ModelKind,
        _current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        return registry.latest(kind)

    return resolve


def _earliest_resolver(
    registry: Registry[VersionValue, ModelBase],
) -> TargetResolver:
    def resolve(
        kind: ModelKind,
        _current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        return registry.earliest(kind)

    return resolve


def _model_resolver(
    registry: Registry[VersionValue, ModelBase],
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
        _current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        if kind != target.kind:
            raise RegistryError(
                registry.name,
                f"Target model {model_cls.__name__} belongs to kind "
                f"{target.kind!r}, but entry kind is {kind!r}",
            )
        return target

    return resolve


def _versionable_resolver(
    target: Versionable[VersionValue_co, VModel_co],
) -> TargetResolver:
    def resolve(
        kind: ModelKind,
        _current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        if kind != target.kind:
            raise RegistryError(
                "target",
                f"Target {target} belongs to kind {target.kind!r}, "
                f"but entry kind is {kind!r}",
            )
        return target

    return resolve


def _string_resolver(
    registry: Registry[VersionValue, ModelBase],
    value: str,
    adapter: ModelAdapter,
) -> TargetResolver:
    """Resolve an explicit version string to a registered versionable.

    The string is parsed eagerly with the adapter's version parser, which
    understands both semver and ISO date values.  Resolving against an
    unregistered version raises ``ModelNotFoundError``; an unparsable value
    fails fast here.
    """
    try:
        parsed = adapter.of(value)
    except ValueError:
        raise RegistryError(
            registry.name,
            f"Could not resolve string target {value!r} to a version",
        ) from None

    def resolve(
        kind: ModelKind,
        _current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        sentinel: Versionable[VersionValue_co, VModel_co] = cast(
            Versionable[VersionValue_co, VModel_co],
            SentinelNode(kind, parsed),
        )
        return registry.get_model(sentinel)

    return resolve
