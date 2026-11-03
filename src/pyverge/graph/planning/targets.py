from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar, cast

from pyverge.core.types import (
    ModelHandle,
    ModelKind,
    TargetResolver,
    VersionValue,
    VersionValue_co,
)
from pyverge.core.versioning import (
    NodeRef,
    Versionable,
    VersionKey,
    VersionNode,
    parse_version,
)
from pyverge.graph.types import GraphView
from pyverge.registry.errors import CatalogError, ModelNotFoundError
from pyverge.schemas.types import ModelIdentityPort

TargetStrategy = Literal["latest", "earliest", "skip"]

ContextT_contra = TypeVar("ContextT_contra", contravariant=True)


class TargetSelector(Protocol[ContextT_contra]):
    """Select one target policy from a transport-specific context."""

    def select(self, context: ContextT_contra) -> TargetPolicy | None: ...


class DefaultTarget(Generic[ContextT_contra]):
    """Always select the fallback target."""

    def __init__(self, target: TargetPolicy) -> None:
        self._target = target

    def select(self, context: ContextT_contra) -> TargetPolicy | None:
        return self._target


class FirstMatch(Generic[ContextT_contra]):
    """Return the first non-``None`` selection from the configured selectors."""

    def __init__(self, *selectors: TargetSelector[ContextT_contra]) -> None:
        self._selectors = selectors

    def select(self, context: ContextT_contra) -> TargetPolicy | None:
        for selector in self._selectors:
            target = selector.select(context)
            if target is not None:
                return target
        return None


@dataclass(frozen=True, slots=True)
class VersionRange:
    """A bounded version range that resolves to its highest matching version.

    ``eq`` wins over the bounds, mirroring FastMCP's ``VersionSpec``.
    """

    gte: str | None = None
    lt: str | None = None
    eq: str | None = None

    def matches(self, version: VersionValue | str) -> bool:
        """Return whether *version* falls inside the range."""
        parsed = parse_version(version)
        if self.eq is not None:
            return parsed == parse_version(self.eq)
        if self.gte is not None and parsed < parse_version(self.gte):
            return False
        if self.lt is not None and parsed >= parse_version(self.lt):
            return False
        return True


TargetSpec = (
    VersionRange
    | Versionable[VersionValue_co]
    | type[ModelHandle]
    | TargetStrategy
    | str
    | None
)
TargetPolicy = (
    TargetSpec
    | dict[ModelKind | Literal["*"], TargetSpec]
    | TargetResolver[VersionValue_co]
)


def skip_target_resolver(
    registry: GraphView[VersionValue],
) -> TargetResolver:

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        return None

    return resolve


def latest_target_resolver(
    registry: GraphView[VersionValue],
) -> TargetResolver:

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        return registry.latest(current.kind)

    return resolve


def earliest_target_resolver(
    registry: GraphView[VersionValue],
) -> TargetResolver:

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        return registry.earliest(current.kind)

    return resolve


def range_target_resolver(
    registry: GraphView[VersionValue],
    version_range: VersionRange,
) -> TargetResolver:

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        matched = [
            version
            for version in registry.kind_versions(current.kind)
            if version_range.matches(version.version)
        ]
        return matched[-1] if matched else None

    return resolve


def fixed_target_resolver(
    registry: GraphView[VersionValue],
    target: VersionNode[VersionValue],
) -> TargetResolver:
    if not registry.has_model(target):
        raise CatalogError(
            registry.namespace,
            f"Target {target} is not registered",
        )

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        if current.kind != target.kind:
            raise CatalogError(
                registry.namespace,
                f"Target {target} belongs to kind {target.kind!r}, "
                f"but entry kind is {current.kind!r}",
            )
        return target

    return resolve


def multi_target_resolver(
    resolvers: dict[ModelKind | Literal["*"], TargetResolver],
) -> TargetResolver:
    fallback = resolvers.get("*")
    by_kind: dict[ModelKind, TargetResolver] = {
        k: v for k, v in resolvers.items() if k != "*"
    }

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        resolver = by_kind.get(current.kind, fallback)
        if resolver is None:
            return None
        return resolver(current)

    return resolve


@dataclass(frozen=True, slots=True)
class TargetCompiler(Generic[VersionValue]):
    """Compile declarative target policy into a resolver."""

    graph: GraphView[VersionValue]
    adapter: ModelIdentityPort

    def compile(self, target: TargetPolicy) -> TargetResolver:  # noqa: PLR0911
        if callable(target) and not isinstance(target, type):
            return cast("TargetResolver", target)
        if target is None:
            return skip_target_resolver(self.graph)
        if isinstance(target, str):
            if target == "skip":
                return skip_target_resolver(self.graph)
            if target == "latest":
                return latest_target_resolver(self.graph)
            if target == "earliest":
                return earliest_target_resolver(self.graph)
            return self._version_string(target)
        if isinstance(target, type):
            return self._model(target)
        if isinstance(target, VersionRange):
            return range_target_resolver(self.graph, target)
        if isinstance(target, dict):
            return multi_target_resolver(
                {kind: self.compile(spec) for kind, spec in target.items()}
            )
        return fixed_target_resolver(
            self.graph, cast("VersionNode[VersionValue]", target)
        )

    def _model(self, model: type[ModelHandle]) -> TargetResolver:
        try:
            target = self.graph.get_model_by_ref(self.adapter.ref(model))
        except ModelNotFoundError as error:
            raise CatalogError(
                self.graph.namespace,
                f"Target model {model.__name__} is not registered",
            ) from error

        def resolve(
            current: VersionNode[VersionValue],
        ) -> VersionNode[VersionValue] | None:
            if current.kind != target.kind:
                raise CatalogError(
                    self.graph.namespace,
                    f"Target model {model.__name__} belongs to kind "
                    f"{target.kind!r}, but entry kind is {current.kind!r}",
                )
            return target

        return resolve

    def _version_string(self, value: str) -> TargetResolver:
        try:
            parsed = parse_version(value)
        except ValueError:
            raise CatalogError(
                self.graph.namespace,
                f"Could not resolve string target {value!r} to a version",
            ) from None

        def resolve(
            current: VersionNode[VersionValue],
        ) -> VersionNode[VersionValue] | None:
            key = VersionKey[VersionValue](
                namespace=current.namespace,
                kind=current.kind,
                version=parsed,
                ref=NodeRef(),
            )
            return self.graph.get_model(key)

        return resolve
