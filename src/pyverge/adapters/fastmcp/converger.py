"""Converger — route and converge tool calls for a single manager.

One manager per source: the adapter binds exactly one bounded context, so there
is no manager routing to do — only call-time convergence. The converger answers
the per-call questions: which version was called, which physical handler serves
it, and how the payload converges there. It reads the ``_physical`` tool index
and the ``_paths`` precomputed by
:class:`~pyverge.adapters.fastmcp.registry.ToolRegistry` — no graph rebuild and
no per-call policy resolution.

A versioned call is fully served by the converging delegate; an unversioned call
converges only its embedded versioned entries and forwards to the tool's own
handler.
"""

from __future__ import annotations

from typing import Any

from pyverge.manager import Manager
from pyverge.types import ModelData

_KIND_PROPS = ("kind", "version")


class Converger:
    """Resolve delegates and converge payloads for a single manager."""

    def __init__(
        self,
        manager: Manager,
        *,
        policies: dict[str, str] | None = None,
        fallback_policy: str | None = None,
        physical: dict,
        paths: dict,
    ) -> None:
        self.manager = manager
        self._policies = policies or {}
        self._fallback_policy = fallback_policy
        self._physical = physical
        self._paths = paths

    def policy_for(self, kind: str) -> str | None:
        """Return the recorded policy for *kind*, or ``None`` when disabled.

        The fallback is disabled by default: a kind only becomes versioned when
        it is explicitly listed in ``policies`` or a fallback policy was opted
        into at construction.
        """
        return self._policies.get(kind, self._fallback_policy)

    def owns(self, kind: str) -> bool:
        """Return whether the manager has any registered version for *kind*."""
        return bool(self.manager.list_versions(kind))

    def path(self, kind: str, version: str) -> str | None:
        return self._paths.get((kind, version))

    def delegate(self, kind: str, version: str):
        """Return a converging delegate for a call to *kind@version*.

        The delegate converges the call's arguments to the version's policy
        target and invokes the **target's** physical handler, so the consumer
        always gets the tool's current behavior. Returns ``None`` when no
        convergence path is precomputed for the version, or the kind is not
        owned by the manager.
        """
        target = self._paths.get((kind, version))
        if target is None:
            return None
        if not self._physical_for(kind, target):
            return None
        return self.make_indirection(kind, version, target)

    def converge_payload(self, arguments: dict) -> dict | None:
        """Converge an unversioned tool's arguments to the latest models.

        A plain tool (no version param, no versioned chain of its own) may still
        embed versioned models in its arguments. When any embedded kind is owned
        by the manager, the arguments converge to the latest version of every
        registered chain. Returns ``None`` when the payload is not versioned.
        """
        if not self._owns_payload(arguments):
            return None
        return self.manager.migrate(arguments, target={"*": "latest"})

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
        versioned entry found in the payload (nested models embedded in a tool's
        arguments) converges to the latest version of its own chain via the
        ``"*"`` fallback.
        """
        return self.manager.migrate(payload, target={kind: target, "*": "latest"})

    def _owns_payload(self, value: Any) -> bool:
        """Return whether the manager owns the first versioned kind in *value*."""
        found = self._first_kind(value)
        return found is not None and self.owns(found)

    def _first_kind(self, value: Any) -> str | None:
        if isinstance(value, dict):
            kind = value.get(_KIND_PROPS[0])
            version = value.get(_KIND_PROPS[1])
            if isinstance(kind, str) and isinstance(version, str) and self.owns(kind):
                return kind
            for nested in value.values():
                found = self._first_kind(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = self._first_kind(item)
                if found is not None:
                    return found
        return None

    def _physical_for(self, kind: str, target: str) -> Any:
        physical = self._physical.get((kind, target))
        if physical is not None:
            return physical
        owners = sorted(v for (k, v) in self._physical if k == kind)
        return self._physical[(kind, owners[-1])]
