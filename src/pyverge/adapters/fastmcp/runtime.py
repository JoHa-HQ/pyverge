"""FastMCP convergence runtime bridge."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from fastmcp.server.dependencies import get_context, resolve_dependencies

from pyverge.adapters.runtime import ConvergenceRuntime
from pyverge.core.types import ModelData
from pyverge.manager import Manager
from pyverge.manager.types import TargetPolicy
from pyverge.runtime.context import MigrationContext


class Converger:
    """Bind virtual FastMCP components to the shared convergence runtime."""

    def __init__(self, runtime: ConvergenceRuntime) -> None:
        self._runtime = runtime
        self._manager: Manager = runtime.manager
        self._kind = self._manager.adapter.kind_property
        self._version = self._manager.adapter.version_property

    def bind(self, runner: Any) -> None:
        """Bind the runner created by the provider lifespan."""
        self._runtime.bind(runner)

    def _context_for_call(self) -> MigrationContext | None:
        try:
            current = get_context()
        except RuntimeError:
            current = None
        return self._runtime.context_for(current)

    def delegate(
        self,
        *,
        kind: str,
        version: str,
        target: TargetPolicy,
        handler: Callable[..., Any],
    ) -> Callable[..., Any]:

        async def converge(**kwargs: Any) -> Any:
            payload: ModelData = {self._kind: kind, self._version: version, **kwargs}
            result = await self._runtime.converge(
                payload,
                target,
                max_depth=-1,
                context=self._context_for_call(),
            )
            converged = result
            converged.pop(self._kind, None)
            converged.pop(self._version, None)
            async with resolve_dependencies(handler, converged) as resolved:
                output = handler(**resolved)
                if inspect.isawaitable(output):
                    output = await output
                return output

        return converge


__all__ = ["Converger"]
