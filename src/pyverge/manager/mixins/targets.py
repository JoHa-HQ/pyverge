from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, Literal, cast

from pyverge.core.exceptions import ModelNotFoundError, RegistryError
from pyverge.core.versioning import VersionNode
from pyverge.migration.engine import Engine
from pyverge.migration.policy import (
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from pyverge.types import (
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

if TYPE_CHECKING:
    from pydantic import BaseModel

    from . import ManagerState


class TargetResolutionMixin(Generic[VersionValue]):
    """Bound target-resolution helpers shared by the public manager.

    The concrete manager supplies ``engine`` and the class-level
    ``_default_engine``; this mixin only turns declarative target specifications
    into resolvers, keeping the public facade focused on orchestration.
    """

    @singledispatchmethod
    @classmethod
    def compile_target_spec(
        cls: type[ManagerState[VersionValue]],
        spec: TargetSpec,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Compile a single declarative target spec into a resolver closure.

        This base handler is the fallback: any spec that is not ``None``, a
        string or a model class is treated as an explicit versionable target.
        Reading it as a versionable avoids an ``isinstance(spec, Versionable)``
        protocol check, which would trigger the strict ``__eq__`` semantics of
        :class:`VersionNode`.
        """
        engine = engine or cls._default_engine
        return fixed_target_resolver(engine.registry, cast(Versionable, spec))

    @compile_target_spec.register(type(None))
    @classmethod
    def _compile_skip(
        cls: type[ManagerState[VersionValue]],
        spec: None,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Compile ``None`` — or ``"skip"`` — into a resolver that skips entries."""
        engine = engine or cls._default_engine
        return skip_target_resolver(engine.registry)

    @compile_target_spec.register(str)
    @classmethod
    def _compile_string(
        cls: type[ManagerState[VersionValue]],
        spec: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Compile a named (``skip``/``latest``/``earliest``) or version string."""
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
        cls: type[ManagerState[VersionValue]],
        spec: type[ModelBase],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Compile a model class into the resolver for its registered version."""
        engine = engine or cls._default_engine
        return cls._model_resolver(spec, engine=engine)

    @classmethod
    def _model_resolver(
        cls: type[ManagerState[VersionValue]],
        model_cls: type[BaseModel],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Resolve a model class target to its registered versionable."""
        engine = engine or cls._default_engine
        registry = engine.registry

        try:
            target = engine.get_model_by_class(model_cls)
        except ModelNotFoundError as exc:
            raise RegistryError(
                registry.name,
                f"Target model {model_cls.__name__} is not registered",
            ) from exc

        def resolve(
            current: Versionable[VersionValue_co, VModel_co],
        ) -> Versionable[VersionValue_co, VModel_co] | None:
            if current.kind != target.kind:
                raise RegistryError(
                    registry.name,
                    f"Target model {model_cls.__name__} belongs to kind "
                    f"{target.kind!r}, but entry kind is {current.kind!r}",
                )
            return target

        return resolve

    @classmethod
    def _string_resolver(
        cls: type[ManagerState[VersionValue]],
        value: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Resolve an explicit version string to a registered versionable."""
        engine = engine or cls._default_engine
        registry = engine.registry
        adapter = engine.adapter

        try:
            parsed = adapter.of(value)
        except ValueError:
            raise RegistryError(
                registry.name,
                f"Could not resolve string target {value!r} to a version",
            ) from None

        def resolve(
            current: Versionable[VersionValue_co, VModel_co],
        ) -> Versionable[VersionValue_co, VModel_co] | None:
            sentinel: Versionable[VersionValue_co, VModel_co] = cast(
                Versionable[VersionValue_co, VModel_co],
                VersionNode[VersionValue_co, VModel_co](
                    _model=None, _value=parsed, _kind=current.kind
                ),
            )
            return engine.get_model(sentinel)

        return resolve

    @classmethod
    def _resolve_kind_mapping(
        cls: type[ManagerState[VersionValue]],
        mapping: dict[ModelKind | Literal["*"], TargetSpec],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Compile a per-kind target mapping into a single resolver.

        The special key ``"*"`` is used as the fallback for kinds not
        explicitly listed.
        """
        engine = engine or cls._default_engine
        resolvers: dict[ModelKind | Literal["*"], TargetResolver] = {
            kind: cls.compile_target_spec(spec, engine=engine)
            for kind, spec in mapping.items()
        }
        return multi_target_resolver(resolvers)

    @singledispatchmethod
    @classmethod
    def _resolve_target_policy(
        cls: type[ManagerState[VersionValue]],
        target: TargetPolicy,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Base: an existing callable resolver, else compile it as a spec."""
        engine = engine or cls._default_engine
        if callable(target):
            return cast(TargetResolver, target)
        return cls.compile_target_spec(cast(TargetSpec, target), engine=engine)

    @_resolve_target_policy.register(type)
    @classmethod
    def _policy_for_type(
        cls: type[ManagerState[VersionValue]],
        target: type,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Resolve a model class to its version, else keep a bare class as-is."""
        engine = engine or cls._default_engine
        if issubclass(target, ModelBase):
            return cls.compile_target_spec(target, engine=engine)
        # A bare class is callable: preserve the old resolver fallback.
        return cast(TargetResolver, target)

    @_resolve_target_policy.register(dict)
    @classmethod
    def _policy_for_mapping(
        cls: type[ManagerState[VersionValue]],
        target: dict,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Resolve a per-kind target mapping into a single resolver."""
        engine = engine or cls._default_engine
        return cls._resolve_kind_mapping(
            cast(dict[ModelKind | Literal["*"], TargetSpec], target), engine=engine
        )

    @_resolve_target_policy.register(str)
    @classmethod
    def _policy_for_string(
        cls: type[ManagerState[VersionValue]],
        target: str,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> TargetResolver:
        """Resolve a named (``skip``/``latest``/``earliest``) or version string."""
        engine = engine or cls._default_engine
        return cls.compile_target_spec(target, engine=engine)
