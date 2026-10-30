from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, Literal, cast

from pyverge.core.types import (
    ModelKind,
    TargetResolver,
    VersionValue,
)
from pyverge.engine import Engine
from pyverge.graph.planning.targets import (
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from pyverge.manager.types import (
    TargetPolicy,
    TargetSpec,
)
from pyverge.registry.errors import CatalogError, ModelNotFoundError
from pyverge.schemas.types import (
    ModelHandle,
)
from pyverge.versioning import (
    VersionKey,
    VersionNode,
    parse_version,
)

from ..descriptors import hybridmethod

if TYPE_CHECKING:
    from pyverge.manager.manager import Manager


class TargetResolutionMixin(Generic[VersionValue]):
    """Bound target-resolution helpers shared by the public manager.

    The concrete manager supplies ``engine`` and the class-level
    ``_default_engine``; this mixin only turns declarative target specifications
    into resolvers, keeping the public facade focused on orchestration.
    """

    @hybridmethod
    @singledispatchmethod
    @classmethod
    def compile_target_spec(
        cls: type[Manager[VersionValue]],
        spec: TargetSpec,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        return fixed_target_resolver(engine.registry, cast(VersionNode, spec))

    @compile_target_spec.register(type(None))
    @classmethod
    def _compile_skip(
        cls: type[Manager[VersionValue]],
        spec: None,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        return skip_target_resolver(engine.registry)

    @compile_target_spec.register(str)
    @classmethod
    def _compile_string(
        cls: type[Manager[VersionValue]],
        spec: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        if spec == "skip":
            return skip_target_resolver(engine.registry)
        if spec == "latest":
            return latest_target_resolver(engine.registry)
        if spec == "earliest":
            return earliest_target_resolver(engine.registry)
        return cls._string_resolver(spec, engine=engine)

    @compile_target_spec.register(type)
    @classmethod
    def _compile_model(
        cls: type[Manager[VersionValue]],
        spec: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        return cls._model_resolver(spec, engine=engine)

    @classmethod
    def _model_resolver(
        cls: type[Manager[VersionValue]],
        model_cls: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        registry = engine.registry

        try:
            target = engine.get_model_by_class(model_cls)
        except ModelNotFoundError as exc:
            raise CatalogError(
                registry.name,
                f"Target model {model_cls.__name__} is not registered",
            ) from exc

        def resolve(
            current: VersionNode[VersionValue],
        ) -> VersionNode[VersionValue] | None:
            if current.kind != target.kind:
                raise CatalogError(
                    registry.name,
                    f"Target model {model_cls.__name__} belongs to kind "
                    f"{target.kind!r}, but entry kind is {current.kind!r}",
                )
            return target

        return resolve

    @classmethod
    def _string_resolver(
        cls: type[Manager[VersionValue]],
        value: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        registry = engine.registry
        try:
            parsed = parse_version(value)
        except ValueError:
            raise CatalogError(
                registry.name,
                f"Could not resolve string target {value!r} to a version",
            ) from None

        def resolve(
            current: VersionNode[VersionValue],
        ) -> VersionNode[VersionValue] | None:
            key = VersionKey[VersionValue](
                namespace=current.namespace,
                kind=current.kind,
                version=parsed,
            )
            return engine.get_model(key)

        return resolve

    @classmethod
    def _resolve_kind_mapping(
        cls: type[Manager[VersionValue]],
        mapping: dict[ModelKind | Literal["*"], TargetSpec],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        resolvers: dict[ModelKind | Literal["*"], TargetResolver] = {
            kind: cls.compile_target_spec(spec, engine=engine)
            for kind, spec in mapping.items()
        }
        return multi_target_resolver(resolvers)

    @singledispatchmethod
    @classmethod
    def _resolve_target_policy(
        cls: type[Manager[VersionValue]],
        target: TargetPolicy,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        if callable(target):
            return cast(TargetResolver, target)
        return cls.compile_target_spec(cast(TargetSpec, target), engine=engine)

    @hybridmethod
    @classmethod
    def resolve_target_model(
        cls: type[Manager[VersionValue]],
        declared: ModelHandle,
        target: TargetPolicy,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> ModelHandle | None:
        engine = engine or cls._default_engine
        anchor = engine.get_model_by_class(declared)
        resolver = cls._resolve_target_policy(target, engine=engine)
        resolved = resolver(anchor)
        return (
            engine.adapter.resolve(resolved.descriptor.ref)
            if resolved is not None
            else None
        )

    @_resolve_target_policy.register(type)
    @classmethod
    def _policy_for_type(
        cls: type[Manager[VersionValue]],
        target: type,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        if engine.adapter.identify(target):
            return cls.compile_target_spec(target, engine=engine)
        # A bare class is callable: preserve the old resolver fallback.
        return cast(TargetResolver, target)

    @_resolve_target_policy.register(dict)
    @classmethod
    def _policy_for_mapping(
        cls: type[Manager[VersionValue]],
        target: dict,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        return cls._resolve_kind_mapping(
            cast(dict[ModelKind | Literal["*"], TargetSpec], target), engine=engine
        )

    @_resolve_target_policy.register(str)
    @classmethod
    def _policy_for_string(
        cls: type[Manager[VersionValue]],
        target: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        return cls.compile_target_spec(target, engine=engine)
