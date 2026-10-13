from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyverge.core.types import (
    ModelData,
)
from pyverge.manager import Manager
from pyverge.manager.types import (
    TargetPolicy,
)

_KIND = "kind"
_VERSION = "version"


class Converger:
    """The contract between a virtual component and a version.

    :meth:`delegate` binds a version's converging callable to its anchor handler.
    """

    def __init__(self, manager: Manager) -> None:
        self._manager = manager

    def delegate(
        self,
        *,
        kind: str,
        version: str,
        target: TargetPolicy,
        handler: Callable[..., Any],
    ) -> Callable[..., Any]:
        """The callable a virtual ``kind@version`` component runs.

        Converges the call's arguments from *version* following *target* — the
        full policy, so embedded kinds converge per their own target too — drops
        the identity fields, and invokes *handler* with the converged payload.
        """

        def converge(**kwargs: Any) -> Any:
            payload: ModelData = {_KIND: kind, _VERSION: version, **kwargs}
            converged = self._manager.migrate(payload, target=target)
            converged.pop(_KIND, None)
            converged.pop(_VERSION, None)
            return handler(**converged)

        return converge


__all__ = ["Converger"]
