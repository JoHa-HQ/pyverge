from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Generic

from pyverge.core.registry.errors import MigrationNotFoundError
from pyverge.core.types import Attachable, MigrationFunc, VersionValue
from pyverge.core.versioning import (
    EdgeId,
    HookRef,
    MigrationDescriptor,
)


@dataclass(frozen=True, slots=True)
class HookRefFactory:
    """Callable factory for hook metadata."""

    def __call__(self, hook: Attachable) -> HookRef:
        provider_id = getattr(hook, "provider_id", type(hook).__module__)
        entity_id = getattr(hook, "entity_id", type(hook).__qualname__)
        config = getattr(hook, "config", {})
        if not isinstance(config, Mapping):
            config = {}
        return HookRef(
            provider_id=str(provider_id),
            entity_id=str(entity_id),
            config=dict(config),
        )


@dataclass(frozen=True, slots=True)
class MigrationBinding:
    """Runtime callable bound to one migration edge."""

    func: MigrationFunc
    descriptor: MigrationDescriptor


@dataclass(frozen=True, slots=True)
class HookBinding:
    """Runtime hook bound to one migration edge."""

    hook: Attachable
    ref: HookRef


@dataclass
class MigrationBindings(Generic[VersionValue]):
    """Mutable registration-time bindings owned by the runtime."""

    name: str
    hook_refs: HookRefFactory = field(default_factory=HookRefFactory)
    migrations: dict[EdgeId[VersionValue], MigrationBinding] = field(
        default_factory=dict
    )
    hooks_by_edge: dict[EdgeId[VersionValue], list[HookBinding]] = field(
        default_factory=dict
    )

    def store_migration(
        self,
        edge: EdgeId[VersionValue],
        func: MigrationFunc,
        descriptor: MigrationDescriptor,
    ) -> MigrationBinding:
        binding = MigrationBinding(func=func, descriptor=descriptor)
        self.migrations[edge] = binding
        return binding

    def add_hook(
        self,
        edge: EdgeId[VersionValue],
        hook: Attachable,
    ) -> HookBinding:
        binding = HookBinding(hook=hook, ref=self.hook_refs(hook))
        self.hooks_by_edge.setdefault(edge, []).append(binding)
        return binding

    def resolve(self, edge: EdgeId[VersionValue]) -> MigrationBinding:
        try:
            return self.migrations[edge]
        except KeyError:
            raise MigrationNotFoundError(self.name, edge.key) from None

    def hooks(self, edge: EdgeId[VersionValue]) -> Sequence[HookBinding]:
        return tuple(self.hooks_by_edge.get(edge, ()))

    def remove_migration(self, edge: EdgeId[VersionValue]) -> None:
        self.migrations.pop(edge, None)
        self.hooks_by_edge.pop(edge, None)

    def remove_hook(self, edge: EdgeId[VersionValue], ref: HookRef) -> None:
        hooks = self.hooks_by_edge.get(edge)
        if hooks is None:
            return
        self.hooks_by_edge[edge] = [binding for binding in hooks if binding.ref != ref]
        if not self.hooks_by_edge[edge]:
            del self.hooks_by_edge[edge]

    def clear_hooks(self, edge: EdgeId[VersionValue] | None = None) -> None:
        if edge is None:
            self.hooks_by_edge.clear()
        else:
            self.hooks_by_edge.pop(edge, None)

    def copy(self) -> MigrationBindings[VersionValue]:
        return MigrationBindings(
            name=self.name,
            hook_refs=self.hook_refs,
            migrations=dict(self.migrations),
            hooks_by_edge={
                edge: list(bindings) for edge, bindings in self.hooks_by_edge.items()
            },
        )

    def frozen_migrations(self) -> Mapping[EdgeId[VersionValue], MigrationBinding]:
        return MappingProxyType(dict(self.migrations))


__all__ = [
    "HookBinding",
    "HookRefFactory",
    "MigrationBinding",
    "MigrationBindings",
]
