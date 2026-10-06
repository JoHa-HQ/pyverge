from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

from .engine import EngineLifecycleMixin
from .lookup import LookupMixin
from .migrate import MigrateMixin
from .migrations import MigrationStoreMixin
from .models import ModelStoreMixin
from .targets import TargetResolutionMixin

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pydantic import BaseModel

    from pyverge.migration.engine import Engine
    from pyverge.types import (
        Diffable,
        ManagerClassState,
        ManagerInstanceState,
        ManagerMigrationKey,
        MigrationKeyInput,  # noqa: F401
        ModelKind,
        ModelPair,
        TargetPolicy,
        TargetResolver,
        TargetSpec,
        Versionable,
        VersionValue,
        VModel,
    )

    class ManagerState(
        ManagerInstanceState[VersionValue],
        ManagerClassState[VersionValue],
        Protocol[VersionValue],
    ):
        """Typing-only view of the composed manager shared by the mixins."""

        def get_model(
            self,
            key: tuple[ModelKind, VersionValue] | type[VModel],
            *,
            engine: Engine[VersionValue] | None = None,
        ) -> Versionable[VersionValue, VModel]: ...

        def get(
            self,
            kind: ModelKind,
            version: str,
            *,
            engine: Engine[VersionValue] | None = None,
        ) -> Versionable[VersionValue, VModel]: ...

        def missing_references(
            self,
            version: Versionable[VersionValue, VModel],
        ) -> frozenset: ...

        def validate_graph(
            self,
            version: Versionable[VersionValue, VModel] | None = None,
        ) -> None: ...

        def attach_hooks(self, hooks: Iterable) -> None: ...

        @classmethod
        def compile_target_spec(
            cls,
            spec: TargetSpec,
            *,
            engine: Engine[VersionValue] | None = None,
        ) -> TargetResolver: ...

        @classmethod
        def diff(
            cls,
            key: ModelPair | ManagerMigrationKey,
            *,
            engine: Engine[VersionValue] | None = None,
        ) -> Diffable[VersionValue]: ...

        @classmethod
        def _resolve_kind_mapping(
            cls,
            mapping: dict[ModelKind | Literal["*"], TargetSpec],
            *,
            engine: Engine[VersionValue] | None = None,
        ) -> TargetResolver: ...

        @classmethod
        def _resolve_target_policy(
            cls,
            target: TargetPolicy,
            *,
            engine: Engine[VersionValue] | None = None,
        ) -> TargetResolver: ...

        @classmethod
        def _model_resolver(
            cls,
            model_cls: type[BaseModel],
            *,
            engine: Engine[VersionValue] | None = None,
        ) -> TargetResolver: ...

        @classmethod
        def _string_resolver(
            cls,
            value: str,
            *,
            engine: Engine[VersionValue] | None = None,
        ) -> TargetResolver: ...


__all__ = [
    "EngineLifecycleMixin",
    "LookupMixin",
    "MigrateMixin",
    "MigrationStoreMixin",
    "ModelStoreMixin",
    "TargetResolutionMixin",
]
