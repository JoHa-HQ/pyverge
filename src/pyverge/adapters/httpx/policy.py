"""Client-side HTTP convergence strategy."""

from __future__ import annotations

from dataclasses import dataclass

from pyverge.manager.types import TargetPolicy


@dataclass(frozen=True, slots=True)
class HttpPolicy:
    """One request/response target pair for an HTTP transport.

    A policy belongs to one client/transport pair. Reuse the policy across sync
    and async transports that share the same boundary.
    """

    target: TargetPolicy = "latest"
    response_target: TargetPolicy | None = None


__all__ = ["HttpPolicy"]
