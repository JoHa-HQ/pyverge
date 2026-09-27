"""Converger — call-time routing over the shared bookkeeping.

The converger answers the per-call questions: which version was called, which
physical handler serves it, and how the payload converges there.  It reads the
``_physical`` tool index and the ``_paths`` precomputed by
:class:`~pyverge.adapters.fastmcp.registration.Registrar` — no graph rebuild
and no per-call policy resolution.  A versioned call is fully served by the
converging delegate; an unversioned call converges only its embedded versioned
entries and forwards to the tool's own handler.
"""

from __future__ import annotations

from typing import Any

from pyverge.types import ModelData

from .router import ToolManagerRouter


class Converger:
    """Resolve delegates and converge payloads for versioned tool calls."""

    def __init__(
        self,
        router: ToolManagerRouter,
        *,
        physical: dict,
        paths: dict,
    ) -> None:
        self._router = router
        self._physical = physical
        self._paths = paths

    def path(self, kind: str, version: str) -> str | None:
        return self._paths.get((kind, version))

    def delegate(self, kind: str, version: str):
        """Return a converging delegate for a call to *kind@version*.

        The delegate converges the call's arguments to the version's policy
        target and invokes the **target's** physical handler, so the consumer
        always gets the tool's current behavior.  Returns ``None`` when no
        convergence path is precomputed for the version, or the kind is not
        owned by any manager.
        """
        target = self._paths.get((kind, version))
        if target is None:
            return None
        if not self._physical_for(kind, target):
            return None
        return self.make_indirection(kind, version, target)

    def converge_payload(self, arguments: dict) -> dict | None:
        """Converge an unversioned tool's arguments to the latest models.

        A plain tool (no version param, no versioned chain of its own) may
        still embed versioned models in its arguments.  When any embedded kind
        is owned by a manager, the arguments converge to the latest version of
        every registered chain.  Returns ``None`` when the payload is not
        versioned at all.
        """
        manager = self._router.manager_for_payload(arguments)
        if manager is None:
            return None
        converged: dict = manager.migrate(arguments, target={"*": "latest"})
        return converged

    def make_indirection(self, kind: str, version: str, target: str):
        """Return a handler that converges args, then delegates to the target tool."""

        def handler(**kwargs: Any) -> dict:
            payload: ModelData = {"kind": kind, "version": version, **kwargs}
            converged = self._converge(payload, kind, target)
            converged.pop("kind", None)
            converged.pop("version", None)
            physical = self._physical_for(kind, target)
            fn: Any = getattr(physical, "fn", None) or physical.run
            return fn(**converged)

        return handler

    def _converge(self, payload: ModelData, kind: str, target: str) -> dict:
        """Converge a payload — including nested versioned models — to target.

        The tool's own kind converges to its policy *target*; every other
        versioned entry found in the payload (nested models embedded in a
        tool's arguments) converges to the latest version of its own chain via
        the ``"*"`` fallback.
        """
        manager = self._router.manager_for(kind)
        assert manager is not None, f"no manager owns kind {kind!r}"
        return manager.migrate(
            payload,
            target={kind: target, "*": "latest"},
        )

    def _physical_for(self, kind: str, target: str) -> Any:
        physical = self._physical.get((kind, target))
        if physical is not None:
            return physical
        owners = sorted(
            (v for (k, v) in self._physical if k == kind),
        )
        return self._physical[(kind, owners[-1])]
