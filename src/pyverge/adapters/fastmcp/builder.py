"""Application service: build entrances and virtual components."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from pyverge.runtime.manager import Manager

from .domain import (
    Entrance,
    EntranceKey,
    Policy,
    PolicyValue,
    VersionRange,
    VirtualComponent,
)
from .ports import ComponentKind
from .runtime import Converger

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from pyverge.runtime.manager.types import TargetPolicy


class ComponentBuilder:
    """Build graph entrances from host components and virtuals from versions.

    The builder owns the graph-facing application logic: policy resolution,
    the entrance index, registration through the manager, anchor-handler
    selection, and virtual-component construction. The provider stays a thin
    FastMCP adapter.
    """

    def __init__(
        self,
        manager: Manager,
        kinds: Sequence[ComponentKind],
        fallbacks: Mapping[str, Policy] | None,
        converger: Converger,
    ) -> None:
        self._manager = manager
        self._kinds = tuple(kinds)
        self._sources = {kind.name: kind for kind in self._kinds}
        self._fallbacks = dict(fallbacks or {})
        self._converger = converger
        self._entrances: dict[EntranceKey, Entrance] = {}
        self._projected: set[EntranceKey] = set()

    def _source(self, name: str) -> ComponentKind:
        """Return the component family named *name*.

        Args:
            name: Family name, for example ``"tool"``.

        Returns:
            ComponentKind: The configured family.

        Raises:
            ValueError: If no configured family has that name.
        """
        try:
            return self._sources[name]
        except KeyError:
            raise ValueError(
                f"no component kind named {name!r}; pass one through kinds="
            ) from None

    def add(self, component: Any, *, kind_name: str, explicit: bool) -> Entrance | None:
        """Normalize, index, and register one host component."""
        component_kind = self._source(kind_name)
        kind = component_kind.kind(component)
        fallback = self._fallbacks.get(kind) or self._fallbacks.get("*")
        if fallback is None and explicit:
            fallback = "latest"
        entrance = component_kind.entrance(
            component, policy=fallback, explicit=explicit
        )
        if entrance is None:
            return None
        self._store(entrance)
        self._register(entrance)
        return entrance

    async def sync(self, server: FastMCP) -> None:
        """Index server-owned components, preserving explicit entrances."""
        self._entrances = {
            key: entrance
            for key, entrance in self._entrances.items()
            if entrance.explicit
        }
        for component_kind in self._kinds:
            async for component in component_kind.components(server):
                kind = component_kind.kind(component)
                version = component_kind.version(component)
                if version is None:
                    continue
                key = (kind, version)
                if key in self._entrances or key in self._projected:
                    continue
                self.add(component, kind_name=component_kind.name, explicit=False)

    def policy_for(self, kind: str) -> Policy | None:
        """Return the single policy of *kind*, if any.

        Args:
            kind: Graph kind to inspect.

        Returns:
            Policy | None: The agreed policy, or ``None`` when unindexed.

        Raises:
            ValueError: If versions of the kind declare different policies.
        """
        policies = [
            entrance.policy
            for entrance in self._entrances.values()
            if entrance.kind == kind
        ]
        if any(policy != policies[0] for policy in policies[1:]):
            rendered = ", ".join(repr(policy) for policy in policies)
            raise ValueError(
                f"kind {kind!r} declares conflicting policies "
                f"[{rendered}]; a kind converges to one target"
            )
        return policies[0] if policies else None

    def virtuals(self) -> Iterator[tuple[ComponentKind, VirtualComponent]]:
        """Yield each missing graph version with its bound handler."""
        adapter = self._manager.adapter
        identity = {adapter.kind_property, adapter.version_property}
        for kind, entrances in self._entrances_by_kind().items():
            policy = self.policy_for(kind)
            if policy is None:
                continue
            source = self._sources[entrances[0].source]
            mapping = self._policy_mapping(kind, policy)
            handler = self._anchor_handler(entrances, mapping[kind])
            for version in self._versions_for(kind):
                key = (kind, version)
                if key in self._entrances or key in self._projected:
                    continue
                model = adapter.resolve(self._manager.get(kind, version).descriptor.ref)
                if model is None:
                    continue
                schema = model.model_json_schema()
                schema["properties"] = {
                    name: prop
                    for name, prop in schema.get("properties", {}).items()
                    if name not in identity
                }
                self._projected.add(key)
                yield (
                    source,
                    VirtualComponent(
                        kind=kind,
                        version=version,
                        schema=schema,
                        handler=self._converger.delegate(
                            kind=kind,
                            version=version,
                            target=cast("TargetPolicy", mapping),
                            handler=handler,
                        ),
                    ),
                )

    def _store(self, entrance: Entrance) -> None:
        known = self.policy_for(entrance.kind)
        if known is not None and known != entrance.policy:
            raise ValueError(
                f"kind {entrance.kind!r} declares conflicting policies "
                f"{known!r} and {entrance.policy!r}; a kind converges to one target"
            )
        self._entrances[entrance.key] = entrance

    def _register(self, entrance: Entrance) -> None:
        adapter = self._manager.adapter
        self._manager.reconcile_model(
            adapter.versionable_from_schema(
                entrance.schema,
                kind=entrance.kind,
                version=entrance.version,
            )
        )

    def _entrances_by_kind(self) -> dict[str, list[Entrance]]:
        groups: dict[str, list[Entrance]] = {}
        for entrance in self._entrances.values():
            groups.setdefault(entrance.kind, []).append(entrance)
        return groups

    def _versions_for(self, kind: str) -> list[str]:
        return [str(node.version) for node in self._manager.list_versions(kind)]

    def _anchor_handler(
        self, entrances: Sequence[Entrance], target: str
    ) -> Callable[..., Any]:
        handlers = {
            entrance.version: entrance.handler
            for entrance in entrances
            if entrance.handler is not None
        }
        if target in handlers:
            return handlers[target]
        for version in reversed(self._versions_for(entrances[0].kind)):
            if version in handlers:
                return handlers[version]
        raise ValueError(f"no physical handler for kind {entrances[0].kind!r}")

    def _policy_mapping(self, kind: str, policy: Policy) -> dict[str, str]:
        if isinstance(policy, dict):
            mapping = {
                target: self._resolve_target(kind if target == "*" else target, value)
                for target, value in policy.items()
            }
            mapping.setdefault(kind, mapping.get("*", "latest"))
            return mapping
        return {kind: self._resolve_target(kind, policy)}

    def _resolve_target(self, kind: str, policy: PolicyValue) -> str:
        versions = self._versions_for(kind)
        if isinstance(policy, VersionRange):
            matched = [version for version in versions if policy.matches(version)]
            if not matched:
                raise ValueError(
                    f"no version of kind {kind!r} matches range {policy!r}"
                )
            return matched[-1]
        if policy not in ("latest", "earliest"):
            return policy
        if not versions:
            raise ValueError(f"no registered versions for kind {kind!r}")
        return versions[-1] if policy == "latest" else versions[0]


__all__ = ["ComponentBuilder"]
