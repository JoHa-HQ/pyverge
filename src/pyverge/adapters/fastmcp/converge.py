from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from pyverge.core.types import (
    ModelData,
)
from pyverge.execution.errors import AsyncExecutionRequired
from pyverge.manager import Manager
from pyverge.manager.types import (
    TargetPolicy,
)


class Converger:
    """The contract between a virtual component and a version.

    :meth:`delegate` binds a version's converging callable to its anchor handler.
    """

    def __init__(self, manager: Manager) -> None:
        self._manager = manager
        self._kind = manager.adapter.kind_property
        self._version = manager.adapter.version_property

    def delegate(
        self,
        *,
        kind: str,
        version: str,
        target: TargetPolicy,
        handler: Callable[..., Any],
    ) -> Callable[..., Any]:

        def converge(**kwargs: Any) -> Any:
            payload: ModelData = {self._kind: kind, self._version: version, **kwargs}
            result = self._manager.runner().run(
                payload,
                target,
                container=None,
                max_depth=-1,
                context=None,
            )
            if inspect.isawaitable(result):
                raise AsyncExecutionRequired(
                    "Converger requires a sync runtime backend"
                )
            converged = result
            converged.pop(self._kind, None)
            converged.pop(self._version, None)
            return handler(**converged)

        return converge


__all__ = ["Converger"]
