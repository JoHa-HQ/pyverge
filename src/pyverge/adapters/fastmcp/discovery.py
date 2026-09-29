from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pyverge.core import MissingReferenceError, ModelConflictError
from pyverge.manager import Manager
from pyverge.types import Attachable

from .converge import Converger
from .reflection import ComponentReflection, ReflectedNode


class ToolDiscovery:
    """Index a server's versioned primitives against a manager's graph.

    Owns the lifecycle phases over the reflected-node index:

    * :meth:`search` — traverse the reflection providers and index the nodes
      the manager owns and a policy covers,
    * :meth:`register` — wrap each node's schema, materialize it as its anchor
      model, then validate the registered graph's references,
    * :meth:`enrich` — precompute convergence paths, materialize virtual
      components, attach hooks.

    The ordered lifecycle (which phase, when) is the caller's concern; this
    class only owns the phases. Discovery consumes only
    :class:`~.reflection.ReflectedNode` objects — never a FastMCP primitive — so
    a provider fully owns how its host primitive type is read.
    """

    def __init__(
        self,
        manager: Manager,
        providers: Sequence[ComponentReflection],
        *,
        policies: dict[str, str] | None = None,
        hooks: Sequence[Attachable] = (),
    ) -> None:
        self._manager = manager
        self._providers = tuple(providers)
        self._hooks = tuple(hooks)
        self._policies = dict(policies or {})
        self._nodes: dict[tuple[str, str], ReflectedNode] = {}
        self._converger = Converger(manager)

    def _policy_for(self, kind: str) -> str | None:
        """Return the recorded policy for *kind*, or ``None`` when none exists."""
        return self._policies.get(kind)

    async def search(self, server: Any) -> None:
        """Index every versioned node the manager owns and a policy covers.

        A versioned primitive is indexed only when its kind is owned by the
        manager. A primitive of an unowned kind is unrelated and skipped; a
        primitive whose kind is owned but carries no policy is a
        misconfiguration and fails fast — every exposed kind needs an explicit
        policy. Re-running is idempotent: the index is rebuilt.
        """
        self._nodes.clear()
        for provider in self._providers:
            async for node in provider.reflect(server):
                if not self._manager.list_versions(node.kind):
                    continue
                if self._policy_for(node.kind) is None:
                    raise ValueError(
                        f"versioned primitive {node.kind!r} is owned by the "
                        "manager but has no policy; record one in the discovery "
                        "policies to expose it"
                    )
                self._nodes[(node.kind, node.version)] = node

    def register(self) -> None:
        """Materialize each indexed node's schema as its anchor model, then
        validate the registered graph.

        Registration is unconditional: the engine reconciles a reflected node
        against an already-registered model (identical surface is a no-op, a
        different one raises ``ModelConflictError``), so the reflected schema is
        always validated against the graph contract. A conflict names the host
        primitive that drifted as the error's subject.

        Reference completeness is checked only after every node is stored — it
        is a property of the whole graph, so validating mid-loop would give
        false negatives. ``_reconcile`` remains callable on its own for
        debugging.
        """
        for (kind, version), node in self._nodes.items():
            try:
                self._manager.store_model(node.versionable())
            except ModelConflictError as error:
                raise ModelConflictError(
                    error.registry_name,
                    error.version,
                    error.registered,
                    error.incoming,
                    subject=f"primitive {kind!r}@{version}",
                ) from error
        self._reconcile()

    def _reconcile(self) -> None:
        """Validate the registered graph's references are complete.

        Every versioned kind a registered model references must be registered
        — the walker silently skips unregistered kinds, so a declared-but-absent
        child could never converge. Field agreement is enforced by the engine
        at registration time; reference completeness by ``Manager.validate_graph``.
        A failure names the host primitive that declared the missing reference.
        """
        for kind, version in self._nodes:
            node = self._manager.get(kind, version)
            try:
                self._manager.validate_graph(node)
            except MissingReferenceError as error:
                raise MissingReferenceError(
                    error.registry_name,
                    error.version,
                    error.absent,
                    subject=f"primitive {kind!r}@{version}",
                ) from error

    async def enrich(self, server: Any) -> None:
        """Materialize virtual components and attach hooks.

        Every registered version without a physical primitive gets a virtual
        component that converges calls to the kind's policy target.
        """
        for kind, versions in self._versions_by_kind().items():
            policy = self._policy_for(kind)
            if policy is None:
                continue
            target = self._resolve_target(kind, policy)
            for version in versions:
                if (kind, version) not in self._nodes:
                    self._register_virtual(server, kind, version, target)
        self._attach_hooks()

    def _versions_by_kind(self) -> dict[str, list[str]]:
        kinds: dict[str, list[str]] = {}
        for kind, version in self._nodes:
            kinds.setdefault(kind, []).append(version)
        for versionable in self._manager.list_versions():
            kind, version = str(versionable.version[0]), str(versionable.version[1])
            bucket = kinds.setdefault(kind, [])
            if version not in bucket:
                bucket.append(version)
        return kinds

    def _register_virtual(
        self, server: Any, kind: str, version: str, target: str
    ) -> None:
        adapter = self._manager.adapter
        identity = {adapter.kind_property, adapter.version_property}
        model = self._manager.get(kind, version).model
        schema = model.model_json_schema()
        schema["properties"] = {
            k: v for k, v in schema.get("properties", {}).items() if k not in identity
        }
        provider = self._provider_for(kind)
        provider.virtual(
            server,
            kind,
            version,
            schema,
            self._converger.delegate(
                kind=kind,
                version=version,
                target=target,
                handler=self._anchor_handler(kind, target),
            ),
        )

    def _anchor_handler(self, kind: str, target: str) -> Callable[..., Any]:
        """Return the physical handler a virtual converges calls to.

        Prefers the physical node at *target*; falls back to the kind's newest
        physical version (the target may itself be a virtual version). Raises
        when the kind has no physical node at all.
        """
        node = self._nodes.get((kind, target))
        if node is None:
            owners = sorted(v for (k, v) in self._nodes if k == kind)
            node = self._nodes.get((kind, owners[-1])) if owners else None
        if node is None or node.handler is None:
            raise ValueError(f"no physical handler for kind {kind!r}")
        return node.handler

    def _provider_for(self, kind: str) -> ComponentReflection:
        """Return the provider that owns *kind*.

        A virtual component must converge through the same provider type that
        owns the kind's physical anchor, so call-time routing stays uniform.
        """
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

    def _resolve_target(self, kind: str, policy: str) -> str:
        versions = sorted(self._manager.list_versions(kind), key=lambda v: v.version[1])
        if not versions:
            raise ValueError(f"no registered versions for kind {kind!r}")
        if policy == "latest":
            return str(versions[-1].version[1])
        if policy == "earliest":
            return str(versions[0].version[1])
        return policy

    def _attach_hooks(self) -> None:
        """Attach the observer hooks to every registered migration edge."""
        if not self._hooks:
            return
        self._manager.attach_hooks(self._hooks)

    def converge_payload(self, arguments: dict) -> dict:
        return self._converger.converge_payload(arguments)


__all__ = ["ToolDiscovery"]
