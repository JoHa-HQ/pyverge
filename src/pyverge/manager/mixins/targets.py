from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, Literal, cast

from pyverge.core.types import (
    ModelKind,
    TargetResolver,
    VersionValue,
)
from pyverge.engine import Engine
from pyverge.graph.planning.targets import TargetCompiler
from pyverge.manager.types import (
    TargetPolicy,
    TargetSpec,
)
from pyverge.schemas.types import (
    ModelHandle,
)
from pyverge.versioning import (
    VersionNode,
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

    @classmethod
    def _compiler(cls, engine: Engine[VersionValue]) -> TargetCompiler:
        return TargetCompiler(engine.snapshot(), engine.adapter)

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
        return cls._compiler(engine).compile(cast(VersionNode, spec))

    @compile_target_spec.register(type(None))
    @classmethod
    def _compile_skip(
        cls: type[Manager[VersionValue]],
        spec: None,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        return cls._compiler(engine).compile(None)

    @compile_target_spec.register(str)
    @classmethod
    def _compile_string(
        cls: type[Manager[VersionValue]],
        spec: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        return cls._compiler(engine).compile(spec)

    @compile_target_spec.register(type)
    @classmethod
    def _compile_model(
        cls: type[Manager[VersionValue]],
        spec: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        engine = engine or cls._default_engine
        return cls._compiler(engine).compile(spec)

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
        return cls._compiler(engine).compile(
            cast(dict[ModelKind | Literal["*"], TargetSpec], target)
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
