from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, cast

from pyverge.core.types import (
    ModelHandle,
    ModelKind,
    TargetResolver,
    VersionValue,
    VersionValue_co,
)
from pyverge.registry import (
    GraphCatalog,
)
from pyverge.registry.errors import CatalogError, ModelNotFoundError
from pyverge.schemas.types import ModelAdapter
from pyverge.versioning import Versionable, VersionKey, VersionNode

TargetStrategy = Literal["latest", "earliest", "skip"]
TargetSpec = (
    Versionable[VersionValue_co] | type[ModelHandle] | TargetStrategy | str | None
)
TargetPolicy = (
    TargetSpec
    | dict[ModelKind | Literal["*"], TargetSpec]
    | TargetResolver[VersionValue_co]
)


def skip_target_resolver(
    registry: GraphCatalog[VersionValue],
) -> TargetResolver:

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        return None

    return resolve


def latest_target_resolver(
    registry: GraphCatalog[VersionValue],
) -> TargetResolver:

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        return registry.latest(current.kind)

    return resolve


def earliest_target_resolver(
    registry: GraphCatalog[VersionValue],
) -> TargetResolver:

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        return registry.earliest(current.kind)

    return resolve


def fixed_target_resolver(
    registry: GraphCatalog[VersionValue],
    target: VersionNode[VersionValue],
) -> TargetResolver:
    if not registry.has_model(target):
        raise CatalogError(
            registry.name,
            f"Target {target} is not registered",
        )

    def resolve(
        current: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue] | None:
        if current.kind != target.kind:
            raise CatalogError(
                registry.name,
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

    graph: GraphCatalog[VersionValue]
    adapter: ModelAdapter

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
                self.graph.name,
                f"Target model {model.__name__} is not registered",
            ) from error

        def resolve(
            current: VersionNode[VersionValue],
        ) -> VersionNode[VersionValue] | None:
            if current.kind != target.kind:
                raise CatalogError(
                    self.graph.name,
                    f"Target model {model.__name__} belongs to kind "
                    f"{target.kind!r}, but entry kind is {current.kind!r}",
                )
            return target

        return resolve

    def _version_string(self, value: str) -> TargetResolver:
        try:
            parsed = self.adapter.of(value)
        except ValueError:
            raise CatalogError(
                self.graph.name,
                f"Could not resolve string target {value!r} to a version",
            ) from None

        def resolve(
            current: VersionNode[VersionValue],
        ) -> VersionNode[VersionValue] | None:
            key = VersionKey[VersionValue](_value=parsed, _kind=current.kind)
            return self.graph.get_model(key)

        return resolve
