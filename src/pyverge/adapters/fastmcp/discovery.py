from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from pyverge.core.types import (
    Attachable,
)
from pyverge.discovery import (
    RegisterModel,
    RegisterVersion,
    RegistrationCollector,
)
from pyverge.manager import Manager
from pyverge.registry.errors import MissingReferenceError, ModelConflictError

from .converge import Converger
from .reflection import ComponentReflection, Policy, ReflectedNode
from .source import FastMCPSource

if TYPE_CHECKING:
    from pyverge.manager.types import (
        TargetPolicy,
    )


class FastMCPDiscovery:
    """Index a server's versioned primitives against one manager's graph.

    The lifecycle phases: :meth:`search` traverses the providers and indexes
    the nodes the manager owns; :meth:`register` reflects those nodes through
    ``FastMCPSource`` and validates the graph; :meth:`enrich` materializes the
    virtual surface and attaches hooks. The caller owns the ordering.
    """

    def __init__(
        self,
        manager: Manager,
        providers: Sequence[ComponentReflection],
        *,
        policies: Mapping[str, Policy] | None = None,
        hooks: Sequence[Attachable] = (),
    ) -> None:
        self._manager = manager
        self._providers = tuple(providers)
        self._hooks = tuple(hooks)
        self._policies = dict(policies or {})
        self._nodes: dict[tuple[str, str], ReflectedNode] = {}
        self._declared: dict[str, Policy] = {}
        self._converger = Converger(manager)

    def _policy_for(self, kind: str) -> Policy | None:
        return self._declared.get(kind) or self._policies.get(kind)

    async def search(self, server: Any) -> None:
        self._nodes.clear()
        self._declared.clear()
        for provider in self._providers:
            async for node in provider.reflect(server):
                if not self._manager.list_versions(node.kind):
                    continue
                declared = node.policy or self._policies.get(node.kind)
                if declared is None:
                    raise ValueError(
                        f"versioned primitive {node.kind!r} is owned by the "
                        "manager but has no policy; declare meta={'policy': ...} "
                        "or record one in the discovery policies"
                    )
                self._accept(node, declared)

    def _accept(self, node: ReflectedNode, policy: Policy) -> None:
        existing = self._declared.get(node.kind)
        if existing is not None and existing != policy:
            raise ValueError(
                f"kind {node.kind!r} declares conflicting policies "
                f"{existing!r} and {policy!r}; a kind converges to one target"
            )
        self._declared[node.kind] = policy
        self._nodes[(node.kind, node.version)] = node

    def source(self, server: Any) -> FastMCPSource:
        return FastMCPSource(server, nodes=self._nodes.values())

    async def register(self, server: Any) -> None:
        collector = RegistrationCollector()
        await self.source(server).accept(collector)
        for command in collector.commands:
            try:
                self._manager.engine.register(command)
            except ModelConflictError as error:
                if not isinstance(command, (RegisterModel, RegisterVersion)):
                    raise
                raise ModelConflictError(
                    error.catalog_name,
                    error.version,
                    error.registered,
                    error.incoming,
                    subject=(
                        f"primitive {command.payload.kind!r}@{command.payload.version}"
                    ),
                ) from error
        self._reconcile()

    def _reconcile(self) -> None:
        for kind, version in self._nodes:
            node = self._manager.get(kind, version)
            try:
                self._manager.validate_graph(node)
            except MissingReferenceError as error:
                raise MissingReferenceError(
                    error.catalog_name,
                    error.version,
                    error.absent,
                    subject=f"primitive {kind!r}@{version}",
                ) from error

    async def enrich(self, server: Any) -> None:
        for kind, versions in self._versions_by_kind().items():
            policy = self._policy_for(kind)
            if policy is None:
                continue
            mapping = self._policy_mapping(kind, policy)
            anchor = self._resolve_target(kind, mapping[kind])
            adapter = self._manager.adapter
            identity = {adapter.kind_property, adapter.version_property}
            provider = self._provider_for(kind)
            for version in versions:
                if (kind, version) in self._nodes:
                    continue
                model = adapter.resolve(self._manager.get(kind, version).descriptor.ref)
                if model is None:
                    continue
                schema = model.model_json_schema()
                schema["properties"] = {
                    k: v
                    for k, v in schema.get("properties", {}).items()
                    if k not in identity
                }
                provider.virtual(
                    server,
                    kind,
                    version,
                    schema,
                    self._converger.delegate(
                        kind=kind,
                        version=version,
                        target=cast("TargetPolicy", mapping),
                        handler=self._anchor_handler(kind, anchor),
                    ),
                )
        self._attach_hooks()

    def _versions_by_kind(self) -> dict[str, list[str]]:
        kinds: dict[str, list[str]] = {}
        for kind, version in self._nodes:
            kinds.setdefault(kind, []).append(version)
        for versionable in self._manager.list_versions():
            kind, version = str(versionable.kind), str(versionable.version)
            bucket = kinds.setdefault(kind, [])
            if version not in bucket:
                bucket.append(version)
        return kinds

    def _anchor_handler(self, kind: str, target: str) -> Callable[..., Any]:
        node = self._nodes.get((kind, target))
        if node is None:
            owners = sorted(v for (k, v) in self._nodes if k == kind)
            node = self._nodes.get((kind, owners[-1])) if owners else None
        if node is None or node.handler is None:
            raise ValueError(f"no physical handler for kind {kind!r}")
        return node.handler

    def _provider_for(self, kind: str) -> ComponentReflection:
        providers = {
            p for (k, _), n in self._nodes.items() if k == kind for p in [n.provider]
        }
        if len(providers) == 1:
            return providers.pop()
        if len(providers) > 1:
            raise ValueError(
                f"kind {kind!r} is served by multiple providers; its virtual "
                "component cannot pick one"
            )
        raise ValueError(f"no provider owns kind {kind!r}")

    def _policy_mapping(self, kind: str, policy: Policy) -> dict[str, str]:
        if isinstance(policy, str):
            return {kind: policy}
        mapping = dict(policy)
        mapping.setdefault(kind, mapping.get("*", "latest"))
        return mapping

    def _resolve_target(self, kind: str, policy: str) -> str:
        if policy not in ("latest", "earliest"):
            return policy
        versions = [str(v.version) for v in self._manager.list_versions(kind)]
        if not versions:
            raise ValueError(f"no registered versions for kind {kind!r}")
        return versions[-1] if policy == "latest" else versions[0]

    def _attach_hooks(self) -> None:
        if self._hooks:
            self._manager.attach_hooks(self._hooks)


__all__ = ["FastMCPDiscovery"]
