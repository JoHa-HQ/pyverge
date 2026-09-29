"""Convergence — resolve and run a converging tool call for one manager.

One manager per source: a host binds exactly one bounded context, so there is no
manager routing — only call-time convergence. The converger answers the per-call
questions: which version was called, which handler serves it, and how the
payload converges there. It reads the physical-handler index and the precomputed
paths — no graph rebuild, no per-call policy resolution.

The host supplies a ``handler_for`` callable that turns a physical item into its
callable, so this module stays framework-agnostic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyverge.manager import Manager
from pyverge.types import ModelData

_KIND_PROPS = ("kind", "version")

HandlerFor = Callable[[Any], Callable[..., Any]]


class Converger:
    """Resolve delegates and converge payloads for a single manager."""

    def __init__(
        self,
        manager: Manager,
        *,
        physical: dict,
        paths: dict,
        handler_for: HandlerFor,
        policies: dict[str, str] | None = None,
        fallback_policy: str | None = None,
    ) -> None:
        self.manager = manager
        self._physical = physical
        self._paths = paths
        self._handler_for = handler_for
        self._policies = policies or {}
        self._fallback_policy = fallback_policy

    def policy_for(self, kind: str) -> str | None:
        """Return the recorded policy for *kind*, or ``None`` when disabled."""
        return self._policies.get(kind, self._fallback_policy)

    def owns(self, kind: str) -> bool:
        """Return whether the manager has any registered version for *kind*."""
        return bool(self.manager.list_versions(kind))

    def path(self, kind: str, version: str) -> str | None:
        return self._paths.get((kind, version))

    def delegate(self, kind: str, version: str):
        """Return a converging delegate for a call to *kind@version*, or ``None``."""
        target = self._paths.get((kind, version))
        if target is None or not self._physical_for(kind, target):
            return None
        return self.make_indirection(kind, version, target)

    def converge_payload(self, arguments: dict) -> dict | None:
        """Converge an unversioned payload to the latest models, or ``None``."""
        if not self._owns_payload(arguments):
            return None
        return self.manager.migrate(arguments, target={"*": "latest"})

    def make_indirection(self, kind: str, version: str, target: str):
        """Return a handler that converges args, then calls the target handler."""

        def handler(**kwargs: Any) -> Any:
            payload: ModelData = {"kind": kind, "version": version, **kwargs}
            converged = self._converge(payload, kind, target)
            converged.pop("kind", None)
            converged.pop("version", None)
            return self._handler_for(self._physical_for(kind, target))(**converged)

        return handler

    def _converge(self, payload: ModelData, kind: str, target: str) -> dict:
        return self.manager.migrate(payload, target={kind: target, "*": "latest"})

    def _owns_payload(self, value: Any) -> bool:
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


__all__ = ["Converger", "HandlerFor"]
