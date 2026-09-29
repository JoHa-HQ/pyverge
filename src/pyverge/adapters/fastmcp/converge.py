from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyverge.manager import Manager
from pyverge.types import ModelData

_KIND = "kind"
_VERSION = "version"


class Converger:
    """The contract between a virtual component and a version.

    A virtual ``kind@version`` component and the pyverge graph meet here.
    :meth:`delegate` binds a version's converging callable to its anchor
    handler; :meth:`converge_payload` migrates the embedded versioned entries of
    an unversioned payload. Both route through one manager — a host binds
    exactly one bounded context, so there is no routing to do.
    """

    def __init__(self, manager: Manager) -> None:
        self._manager = manager

    def delegate(
        self,
        *,
        kind: str,
        version: str,
        target: str,
        handler: Callable[..., Any],
    ) -> Callable[..., Any]:
        """Return the callable a virtual ``kind@version`` component runs.

        It converges the call's arguments from *version* to *target* (dropping
        the identity bookkeeping fields) and invokes the anchor *handler* with
        the converged payload.
        """

        def converge(**kwargs: Any) -> Any:
            payload: ModelData = {_KIND: kind, _VERSION: version, **kwargs}
            converged = self._manager.migrate(
                payload, target={kind: target, "*": "latest"}
            )
            converged.pop(_KIND, None)
            converged.pop(_VERSION, None)
            return handler(**converged)

        return converge

    def converge_payload(self, arguments: dict) -> dict:
        """Converge an unversioned payload's embedded versioned entries.

        The manager leaves a payload with nothing to converge untouched, so this
        is safe to run on every call: only entries whose kind is registered
        migrate.
        """
        return self._manager.migrate(arguments, target={"*": "latest"})


__all__ = ["Converger"]
