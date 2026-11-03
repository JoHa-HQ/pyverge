from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Self

from fastmcp.exceptions import FastMCPError
from fastmcp.server.dependencies import get_server
from fastmcp.server.providers import LocalProvider
from fastmcp.server.providers.local_provider.local_provider import DuplicateBehavior

from pyverge.adapters.runtime import ConvergenceRuntime
from pyverge.core.types import (
    Attachable,
)
from pyverge.manager import Manager
from pyverge.registry import HealthFailLevel
from pyverge.registry.errors import HealthValidationError
from pyverge.runtime.context import MigrationContext

from .builder import ComponentBuilder
from .components import DEFAULT_KINDS
from .domain import Policy
from .extension import PyvergeExtension
from .ports import ComponentKind
from .runtime import Converger

if TYPE_CHECKING:
    from fastmcp import FastMCP


class PyvergeProvider(LocalProvider):
    """Index a server's versioned primitives against one manager's graph.

    Components registered on the provider are indexed immediately. Attaching
    the provider to a server is enough: :meth:`lifespan` indexes server-owned
    components, materializes virtual versions when enabled, attaches hooks, and
    applies the health policy before traffic.

    The phases remain public (:meth:`sync`, :meth:`enrich`,
    :meth:`validate_health`) for hosts that own their startup ordering. They are
    idempotent, so a user lifespan and the provider lifespan can both run.
    """

    def __init__(  # noqa: PLR0913
        self,
        manager: Manager,
        *,
        kinds: Sequence[ComponentKind] = DEFAULT_KINDS,
        policies: Mapping[str, Policy] | None = None,
        hooks: Sequence[Attachable] = (),
        virtual_versions: bool = False,
        transforms: Sequence[Any] = (),
        extension: PyvergeExtension | None = None,
        health_fail_level: HealthFailLevel = "error",
        context: MigrationContext | None = None,
        run_id: str | None = None,
        context_factory: Callable[[Any], MigrationContext | None] | None = None,
        validate_target: bool = False,
        on_duplicate: DuplicateBehavior = "error",
    ) -> None:
        super().__init__(on_duplicate=on_duplicate)
        self._manager = manager
        self._hooks = tuple(hooks)
        self._virtual_versions = virtual_versions
        self._server_transforms = tuple(transforms)
        self._server_transformed = False
        self._extension = extension
        self._health_fail_level = health_fail_level
        self._hooked = False
        self._runtime = ConvergenceRuntime(
            manager,
            context=context,
            run_id=run_id,
            context_factory=context_factory,
            validate_target=validate_target,
            health_fail_level=health_fail_level,
        )
        self._converger = Converger(self._runtime)
        self._builder = ComponentBuilder(
            manager,
            kinds,
            policies,
            self._converger,
        )

    @property
    def manager(self: Self) -> Manager:
        return self._manager

    def required_extensions(self) -> Sequence[PyvergeExtension]:
        return () if self._extension is None else (self._extension,)

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None, None]:
        """Prepare the graph and validate health before traffic.

        Attaching the provider is enough: FastMCP enters this lifespan once,
        after user lifespans, and the provider indexes server-owned components,
        materializes virtual versions, and applies the health policy.
        """
        self._converger.bind(self._manager.runner())
        try:
            server = get_server()
        except RuntimeError:
            server = None
        if server is not None:
            await self.sync(server)
            await self.enrich(server)
        self.validate_health()
        async with super().lifespan():
            yield

    def validate_health(self) -> None:
        """Raise FastMCP's startup error when registry health fails.

        Raises:
            FastMCPError: If a registry issue meets the configured fail level.
        """
        try:
            self._runtime.validate_health()
        except HealthValidationError as error:
            raise FastMCPError(str(error)) from error

    def add_tool(self, tool: Any) -> Any:
        """Register a tool and index it against the graph."""
        added = super().add_tool(tool)
        self._builder.add(added, kind_name="tool", explicit=True)
        return added

    def add_prompt(self, prompt: Any) -> Any:
        """Register a prompt and index it against the graph."""
        added = super().add_prompt(prompt)
        self._builder.add(added, kind_name="prompt", explicit=True)
        return added

    def add_resource(self, resource: Any) -> Any:
        """Register a resource and index it against the graph."""
        added = super().add_resource(resource)
        self._builder.add(added, kind_name="resource", explicit=True)
        return added

    def add_template(self, template: Any) -> Any:
        """Register a resource template and index it against the graph."""
        added = super().add_template(template)
        self._builder.add(added, kind_name="resource", explicit=True)
        return added

    async def sync(self, server: FastMCP) -> None:
        """Register server-owned components against the graph.

        The registry reconciles duplicates and refreshes its health index; the
        provider only normalizes FastMCP primitives into graph entrances.
        """
        await self._builder.sync(server)

    async def enrich(self, server: FastMCP) -> None:
        """Materialize virtual versions, attach hooks, then server transforms.

        Transforms run last so a listing transform (for example
        ``VersionFilter``) cannot hide physical components from :meth:`sync`.
        """
        if self._virtual_versions:
            for component_kind, virtual in self._builder.virtuals():
                component_kind.materialize(server, virtual)
        if not self._hooked:
            self._attach_hooks()
            self._hooked = True
        if not self._server_transformed:
            for transform in self._server_transforms:
                server.add_transform(transform)
            self._server_transformed = True

    def _attach_hooks(self) -> None:
        if self._hooks:
            self._manager.attach_hooks(self._hooks)


__all__ = ["PyvergeProvider"]
