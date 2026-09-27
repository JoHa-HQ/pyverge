"""ToolManagerRouter — route a tool kind to the manager that owns it.

The FastMCP adapter supports multiple versioned managers per app (like Django's
multiple databases).  A ``ToolManagerRouter`` binds a set of
:class:`~pyverge.migration.Manager` instances and answers "which manager
owns this kind" — either for an explicit tool kind, or for the first versioned
kind found inside a payload's nested arguments.

Ownership is derived from the registry first (a manager owns a kind it has
registered versions for).  A kind that is *policy-marked* but not yet
registered is claimed by the first manager, so a physical tool can materialize
its own anchor before registration (see :class:`ToolDiscovery`).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pyverge.manager import Manager

_KIND_PROPS = ("kind", "version")


class ToolManagerRouter:
    """Route tool kinds to their owning versioned manager."""

    def __init__(
        self,
        managers: Iterable[Manager],
        *,
        policies: dict[str, str] | None = None,
        fallback_policy: str | None = None,
    ) -> None:
        self._managers = list(managers)
        if not self._managers:
            raise ValueError("ToolManagerRouter requires at least one manager")
        self._policies = policies or {}
        self._fallback_policy = fallback_policy
        self._cache: dict[str, Manager] = {}

    def managers(self) -> list[Manager]:
        """Return the managed instances, in ownership-priority order."""
        return list(self._managers)

    def policy_for(self, kind: str) -> str | None:
        """Return the recorded policy for *kind*, or ``None`` when disabled.

        The fallback is disabled by default: a kind only becomes versioned when
        it is explicitly listed in ``policies`` or a fallback policy was opted
        into at construction.
        """
        return self._policies.get(kind, self._fallback_policy)

    def owns(self, manager: Manager, kind: str) -> bool:
        """Return whether *manager* has any registered version for *kind*."""
        return bool(manager.list_versions(kind))

    def manager_for(self, kind: str) -> Manager | None:
        """Return the first manager with a registered version for *kind*.

        Ownership is derived from the manager's registry, so the customer can
        register versioned models first and the adapter routes by kind
        automatically.  A policy-marked kind with no registered version is
        claimed by the first manager, letting a physical tool materialize its
        own anchor before the raw registration.  Lookups are cached.
        """
        cached = self._cache.get(kind)
        if cached is not None:
            return cached
        for manager in self._managers:
            if self.owns(manager, kind):
                self._cache[kind] = manager
                return manager
        if self.policy_for(kind) is not None:
            self._cache[kind] = self._managers[0]
            return self._managers[0]
        return None

    def manager_for_payload(self, payload: dict[str, Any]) -> Manager | None:
        """Return a manager owning the first versioned entry in *payload*.

        Plain (unversioned) tools whose arguments embed versioned models need a
        manager to converge the nested entries.  The walker only discovers
        kinds registered in a manager's registry, so the first registered kind
        found anywhere in the payload identifies the owner.
        """
        found = self._first_kind(payload)
        if found is None:
            return None
        return self.manager_for(found)

    def _first_kind(self, value: Any) -> str | None:
        if isinstance(value, dict):
            kind = value.get(_KIND_PROPS[0])
            version = value.get(_KIND_PROPS[1])
            if isinstance(kind, str) and isinstance(version, str):
                owner = self.manager_for(kind)
                if owner is not None:
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
